import os
import time
import sys

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
                        yield entry
                except OSError:
                    continue
        except OSError:
            pass

def scan(path, ffn, dfn):
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_dir() and not entry.is_symlink():
                    ffn(entry.path)
                else:
                    dfn(entry.path)
            except OSError:
                continue
    except OSError:
        pass



async def scandir_async(path):
    """
    Async iterative implementation of os.scandir.
    """
    loop = asyncio.get_event_loop()
    dirs, files = [], []
    scan(path, files.append, dirs.append)
    while dirs:
        for f in files: yield f
        task = asyncio.gather(*(
            loop.run_in_executor(None, scan, d, files.append, dirs.append)
            for d in dirs
        ))
        await task


def display_counter(it):
    i = 0
    start = time.perf_counter()
    for _ in it:
        i+=1
        print('\r', f'Scanned {i} files at {i/(time.perf_counter()-start)}/s', end='')
    print()

async def adisplay_counter(ait):
    i = 0
    start = time.perf_counter()
    async for _ in ait:
        i+=1
        print('\r', f'Scanned {i} files at {i/(time.perf_counter()-start)}/s', end='')
    print()

def main():
    path = sys.argv[1]

    print("Iterative:")
    display_counter(scandir_iterative(path))

    print('Async')
    asyncio.run(adisplay_counter(scandir_async(path)))

if __name__ == "__main__":
    main()
