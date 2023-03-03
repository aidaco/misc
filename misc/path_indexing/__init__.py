import os
import re
from pathlib import Path


def scan(root):
    dirs = [root]
    pop = dirs.pop
    append = dirs.append
    scan = os.scandir
    is_dir = os.DirEntry.is_dir
    while dirs:
        for entry in scan(pop()):
            path = entry.path
            yield path
            if is_dir(entry, follow_symlinks=False):
                append(path)


def scan_safe(root):
    dirs = [root]
    pop = dirs.pop
    append = dirs.append
    scan = os.scandir
    is_dir = os.DirEntry.is_dir
    while dirs:
        try:
            for entry in scan(pop()):
                path = entry.path
                yield path
                try:
                    if is_dir(entry, follow_symlinks=False):
                        append(path)
                except OSError:
                    continue
        except OSError:
            continue


def make_index(
    root: str = "/", path: str = Path.home() / "fspaths.index", scan=scan_safe
):
    with open(path, "w") as file:
        for i, entry in enumerate(scan(root)):
            file.write(entry + "\n")
    return i


def search_index(pat, path=Path.home() / "fspaths.index"):
    pat = re.compile(pat)
    with open(path) as file:
        yield from (ln for ln in file if pat.match(ln))


def search(pat):
    try:
        return list(search_index(pat))
    except:
        make_index()
        return list(search_index(pat))
