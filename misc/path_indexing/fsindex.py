import re
from pathlib import Path
import os


def iterfiles(root):
    dirs = [root]
    while dirs:
        try:
            with os.scandir(dirs.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_file():
                            yield entry.path
                        elif entry.is_dir() and not entry.is_symlink():
                            dirs.append(entry.path)
                    except IOError:
                        continue
        except IOError:
            continue


def create_index(root, path):
    with open(path, "w") as file:
        for path in iterfiles(root):
            file.write(path + "\n")


def iterindex(path):
    with open(path) as file:
        yield from (line.strip() for line in file)


def iterindex_preload(path):
    with open(path) as file:
        content = file.read()

        yield from (line.strip() for line in file)


def chunked(size, it):
    i, chunk = 0, []
    for e in it:
        if i != size:
            chunk.append(e)
            i += 1
        else:
            yield chunk
            i, chunk = 0, []


def search_index(pat, path):
    pat = re.compile(pat)
    yield from (p for p in iterindex(path) if pat.match(p))


def search_index_chunked(pat, path, size=10000):
    pat = re.compile(pat)
    for paths in (
        path
        for chunk in chunked(size, iterindex(path))
        for path in chunk
        if pat.match(path)
    ):
        yield from paths
