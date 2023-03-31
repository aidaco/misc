"""FFI Wrapper for inotify."""

import asyncio
import ctypes
import os
import struct
import tempfile
import typing
from collections import deque
from dataclasses import dataclass
from enum import IntEnum
from functools import reduce
from pathlib import Path


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


class INEvent(IntEnum):
    """Holds INotify mask values."""

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
    def from_mask(cls, mask) -> list["INEvent"]:
        """Converts mask to list of INEvent."""
        return [evt for evt in cls if evt.value & mask]

    @classmethod
    def all(cls) -> int:
        """Default mask to capture all events."""
        return reduce(lambda x, y: int(x) | int(y), cls)


@dataclass
class INMessage:
    size: typing.ClassVar[int] = struct.calcsize("iIII")
    wd: int
    events: list[INEvent]
    cookie: int
    name: str

    @classmethod
    def read(cls, fd: int) -> "INMessage":
        bs = os.read(fd, cls.size)
        if not bs:
            raise ValueError("No data read.")
        w, m, c, l = struct.unpack("iIII", bs)
        if l > 0:
            bs = os.read(fd, l)
            n = os.fsdecode(bytes(bs).rstrip(b"\x00")) if l > 0 else ""
        else:
            n = ""
        e = INEvent.from_mask(m)
        return cls(w, e, c, n)

    @classmethod
    def read_chunk(cls, fd: int, chunk_size: int = 4096) -> list["INMessage"]:
        bs = os.read(fd, chunk_size)
        msgs = []
        while len(bs) >= cls.size:
            w, m, c, l, bs = *struct.unpack("iIII", bs[: cls.size]), bs[cls.size :]
            if l > 0:
                n, bs = os.fsdecode(bytes(bs[:l]).rstrip(b"\x00")), bs[:l]
            else:
                n = ""
            e = INEvent.from_mask(m)
            msgs.append(cls(w, e, c, n))
        return msgs


class INotify:
    in_init, in_add, in_rm = load_fns()

    def __init__(self, *paths: Path, mask: int = INEvent.all()):
        print("IN :: INIT")
        self.pathwds: dict[Path, int] = {}
        self.wdpaths: dict[int, Path] = {}
        self.fd = self.in_init(os.O_NONBLOCK)
        self.closed = False
        if self.fd == -1:
            raise ValueError("Could not initialize inotify.")
        self.add(*paths, mask=mask)

    def add(self, *paths: Path, mask: int = INEvent.all()):
        print("IN :: ADD")
        for path in paths:
            if (wd := self.in_add(self.fd, bytes(path.resolve()), mask)) == -1:
                raise ValueError(f"Adding watch on path {path} failed.")
            self.pathwds[path] = wd
            self.wdpaths[wd] = path

    def rm(self, wd: int):
        if self.in_rm(self.fd, wd) == -1:
            raise ValueError("Nonexistent inotify and/or watch.")
        del self.pathwds[self.wdpaths[wd]]
        del self.wdpaths[wd]

    def read(
        self, chunked: bool = False, chunk_size: int = 4096
    ) -> INMessage | typing.Sequence[INMessage]:
        if chunked:
            return INMessage.read_chunk(self.fd, chunk_size)
        return INMessage.read(self.fd)

    def close(self):
        print("IN :: CLOSE ")
        self.closed = True
        os.close(self.fd)


class watch(INotify):
    def __init__(
        self,
        *paths: Path,
        chunked: bool = False,
        chunk_size: int = 4096,
        mask: int = INEvent.all(),
    ):
        self.paths = paths
        self.mask = mask
        self.chunked = chunked
        self.chunk_size = chunk_size
        if chunked:
            self.msgs: deque = deque()

    def __enter__(self):
        super().__init__(self, *self.paths, mask=self.mask)
        return self

    async def __aenter__(self):
        super().__init__(*self.paths, mask=self.mask)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __iter__(self):
        return self

    def __aiter__(self):
        return self

    def __next__(self):
        while not self.closed:
            try:
                if self.chunked:
                    if not self.msgs:
                        self.msgs.extend(
                            self.read(chunked=True, chunk_size=self.chunk_size)
                        )
                    return self.msgs.pop(0)
                return self.read()
            except BlockingIOError:
                continue
        raise StopIteration

    async def __anext__(self):
        while not self.closed:
            try:
                if self.chunked:
                    if not self.msgs:
                        self.msgs.extend(
                            self.read(chunked=True, chunk_size=self.chunk_size)
                        )
                    return self.msgs.pop(0)
                return self.read()
            except BlockingIOError:
                await asyncio.sleep(0)
        raise StopAsyncIteration


def watcher(
    *paths, mask: int = INEvent.all(), chunked: bool = False, chunk_size: int = 4096
):
    with watch(*paths, mask=mask, chunked=chunked, chunk_size=chunk_size) as w:
        for msg in w:
            yield (msg)


async def asyncwatcher(
    *paths, mask: int = INEvent.all(), chunked: bool = False, chunk_size: int = 4096
):
    try:
        async with watch(
            *paths, mask=mask, chunked=chunked, chunk_size=chunk_size
        ) as w:
            print("ASYNCWATCHER :: WATCHING")
            async for msg in w:
                print("ASYNCWATCHER :: RECVD")
                yield msg
            print("ASYNCWATCHER :: EXITING")
    except asyncio.CancelledError:
        print("ASNYNCWATCHER :: DONE")


async def main():
    events = []
    tmp_dir = Path(tempfile.mkdtemp())

    async def wcoro():
        try:
            print("WCORO :: STARTED")
            async for event in asyncwatcher(tmp_dir):
                print("WCORO :: RECVD")
                events.append(event)
        except asyncio.CancelledError:
            print("WCORO :: DONE")

    task = asyncio.gather(wcoro(), file_operations(tmp_dir))
    await asyncio.sleep(2)
    task.cancel()
    await task
    print("MAIN :: Stopped watcher")
    print("MAIN :: Received Events:")
    print("", *(str(event) for event in events), sep="\n\t")


async def file_operations(dpath):
    print("FILEOPS :: Started")
    with open(dpath / "test1", "w") as f:
        f.write("Hello world")
    (dpath / "test1").unlink()
    (dpath / "test2").touch()
    (dpath / "test2").unlink()
    print("FILEOPS :: Completed")


if __name__ == "__main__":
    asyncio.run(main())
