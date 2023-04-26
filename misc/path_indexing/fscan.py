import asyncio
import os
import sys
import time


def scandir_iterative(path):
    """
    Iterative implementation of os.scandir.
    """
    stack = [path]
    while stack:
        path = stack.pop()
        try:
            for entry in os.scandir(path):
                try:
                    if entry.is_dir() and not entry.is_symlink():
                        stack.append(entry.path)
                    else:
                        yield entry.path
                except OSError:
                    print("Inner error", entry.path)
                    continue
        except OSError:
            print("Outer error", entry.path)
            pass


def scan(path, ffn, dfn):
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir() and not entry.is_symlink():
                    dfn(entry.path)
                else:
                    ffn(entry.path)
            except OSError:
                print("Inner error", entry.path)
                continue
    except OSError:
        print("Outer error", entry.path)
        pass


async def scandir_async(path):
    """
    Async iterative implementation of os.scandir.
    """
    loop = asyncio.get_event_loop()
    dirs, files = [], []
    scan(path, files.append, dirs.append)
    while True:
        for f in files:
            yield f
        cur, dirs = dirs, []
        task = asyncio.gather(
            *(
                loop.run_in_executor(None, scan, d, files.append, dirs.append)
                for d in cur
            )
        )
        await task
        if not dirs:
            break


def display_counter(it):
    i = 0
    start = time.perf_counter()
    for _ in it:
        i += 1
        print("\r", f"Scanned {i} files at {i/(time.perf_counter()-start)}/s", end="")
        yield _
    print()


async def adisplay_counter(ait):
    i = 0
    start = time.perf_counter()
    async for _ in ait:
        i += 1
        print("\r", f"Scanned {i} files at {i/(time.perf_counter()-start)}/s", end="")
        yield _
    print()


def main():
    global iterl, asyncl
    path = sys.argv[1]

    print("Iterative:")
    start = time.perf_counter()
    iterl = list(display_counter(scandir_iterative(path)))
    print(f"Elapsed: {time.perf_counter()-start:0.2f}")

    print("Async")

    async def run():
        return [e async for e in adisplay_counter(scandir_async(path))]

    start = time.perf_counter()
    asyncl = asyncio.run(run())
    print(f"Elapsed: {time.perf_counter()-start:0.2f}")


if __name__ == "__main__":
    main()
