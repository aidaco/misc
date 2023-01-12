import time
import threading
from threading import Thread
import os
import asyncio
import itertools
import queue
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from collections import deque


def iscan(path):
    dirs = [path]
    dappend = dirs.append
    while dirs:
        try:
            with os.scandir(dirs.pop(0)) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            dappend(entry)
                        else:
                            yield entry
                    except IOError:
                        continue
        except IOError:
            continue


def read_paths(cancel, path_queue, file_queue):
    while not cancel.is_set():
        try:
            path = path_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        ds, fs = split_dirs(scandir(path))
        [path_queue.put(d) for d in ds]
        [file_queue.put(f) for f in fs]
        path_queue.task_done()


def counter(cancel, q):
    i = 0
    while not cancel.is_set():
        try:
            q.get(timeout=0.1)
            i += 1
            print("\r" + f"counted {i} files", end="")
        except queue.Empty:
            continue


def multiscan(path):
    path_queue = queue.Queue()
    path_queue.put(path)
    file_queue = queue.Queue()
    cancel = threading.Event()
    ccancel = threading.Event()
    readers = [
        Thread(target=read_paths, args=(cancel, path_queue, file_queue))
        for _ in range(4)
    ]
    count = Thread(target=counter, args=(cancel, file_queue))
    for r in readers:
        r.start()
    count.start()
    path_queue.join()
    cancel.set()
    for r in readers:
        r.join()
    ccancel.set()
    count.join()


def scandir(path):
    try:
        with os.scandir(path) as it:
            yield from it
    except OSError:
        pass


def split_dirs(entries):
    dirs, files = [], []
    dappend, fappend = dirs.append, files.append
    for entry in entries:
        try:
            if entry.is_dir():
                dappend(entry.path)
            else:
                fappend(entry.path)
        except OSError as e:
            continue
    return dirs, files


async def _indexthreaded(path, loop=None, executor=None):
    loop = loop if loop is not None else asyncio.get_event_loop()
    executor = executor if executor is not None else ThreadPoolExecutor()
    files, dirs = await loop.run_in_executor(executor, scandir, path)
    while dirs:
        tasks = (loop.run_in_executor(executor, multiscan, d) for d in dirs)
        for fs, ds in await asyncio.gather(*tasks):
            files += fs
            dirs += ds


def _collect(seq_it):
    elems = []
    for elem in seq_it:
        elems += elem
    return elems


def _index(path):
    return _collect(asyncio.run(_indexthreaded(path)))


async def _indexprocessed(path):
    loop = asyncio.get_event_loop()
    executor = ProcessPoolExecutor()
    files, dirs = scandir(path)
    tasks = (loop.run_in_executor(executor, _index, d) for d in dirs)
    return files + _collect(await asyncio.gather(*tasks))


def indexproc(path):
    return asyncio.run(_indexprocessed(path))


def count(it):
    i = 0
    for _ in it:
        i += 1
    return i


if __name__ == "__main__":
    start = time.perf_counter()
    print(
        f"Indexed {(multiscan(os.getcwd()))} files in {time.perf_counter() - start:.2f}s"
    )
