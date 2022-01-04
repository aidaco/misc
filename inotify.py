import pytest
from dataclasses import dataclass
from queue import Queue
import asyncio
import threading
import multiprocessing
import os
import ctypes
import struct
from pathlib import Path
import tempfile
from functools import reduce, partial
from enum import IntEnum
from typing import ClassVar, Callable
import typing
from rich import print


def call_sequential(*functions):
    def do():
        for f in functions:
            f()

    return do


def compose2(f, g):
    def do(*args, **kwargs):
        return g(f(*args, **kwargs))

    return do


def compose(*functions):
    return reduce(compose2, functions)


def asynccompose2(f, g):
    async def do(*args, **kwargs):
        return await g(await f(*args, **kwargs))

    return do


def asynccompose(*functions):
    async def do(*args, **kwargs):
        return reduce(asynccompose2, functions)(*args, **kwargs)

    return do


def load_fns():
    "Returns inotify functions as: tuple(inotify_init1, inotify_add_watch, inotify_rm_watch)"
    libc = ctypes.CDLL("libc.so.6")
    return (
        ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_uint32)(libc.inotify_init1),
        ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)(
            libc.inotify_add_watch
        ),
        ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.c_int)(
            libc.inotify_rm_watch
        ),
    )


in_init, in_add, in_rm = load_fns()


class INEvent(IntEnum):
    CREATE = 256
    DELETE = 512
    OPEN = 32
    READ = 1
    WRITE = 2
    CLOSE_WRITE = 8
    CLOSE_NOWRITE = 16
    META = 4
    MOVED_FROM = 64
    MOVED_TO = 128
    DELETE_SELF = 1024
    MOVE_SELF = 2048

    @classmethod
    def from_mask(cls, mask):
        return [evt for evt in cls if evt.value & mask]

    @classmethod
    def all(cls):
        return reduce(lambda x, y: x | y, cls)


@dataclass
class INMessage:
    size: ClassVar[int] = struct.calcsize("iIII")
    wd: int
    event: INEvent
    cookie: int
    name: str

    @classmethod
    def unpack_from(cls, data: bytearray):
        if len(data) < cls.size:
            return None
        w, m, c, l = struct.unpack_from("iIII", data)
        n, data = bytes(data[cls.size : cls.size + l]), data[cls.size + l :]
        return cls(w, INEvent.from_mask(m), c, os.fsdecode(n.rstrip(b"\x00"))), data

    @classmethod
    def read_from(cls, fio: typing.BinaryIO):
        bs = fio.read(cls.size)
        w, m, c, l = struct.unpack("iIII", bs)
        if l > 0:
            bs = fio.read(l)
            n = os.fsdecode(bytes(bs).rstrip(b"\x00")) if l > 0 else ""
        else:
            n = ""
        e = INEvent.from_mask(m)
        print(f"INOTIFY :: Parsed: {w=}\t{c=}\t{l=}\n\t{e}\t{n=}")
        return INMessage(w, e, c, n)


class INotify:
    def __init__(self):
        self.pathwds: dict[Path, int] = {}
        self.wdpaths: dict[int, Path] = {}
        fd = in_init(os.O_NONBLOCK)
        print(f"INOTIFY :: Init with {fd=}")
        if fd == -1:
            raise ValueError("Could not initialize inotify.")
        self.fio = open(fd, "rb", closefd=False)

    def add(self, *paths: Path, mask: int = INEvent.all()):
        for path in paths:
            if (wd := in_add(self.fio.fileno(), bytes(path.resolve()), mask)) == -1:
                raise ValueError(f"Adding watch on path {path} failed.")
            print(f"INOTIFY :: Watching {path} for {INEvent.from_mask(mask)}")
            self.pathwds[path] = wd
            self.wdpaths[wd] = path

    def rm(self, wd: int):
        if in_rm(self.fio.fileno(), wd) == -1:
            raise ValueError("Nonexistent inotify and/or watch.")
        del self.pathwds[self.wdpaths[wd]]
        del self.wdpaths[wd]

    def read(self):
        return INMessage.read_from(self.fio)

    def close(self):
        self.fio.close()

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            try:
                evt = self.read()
                return evt
            except BlockingIOError:
                continue
