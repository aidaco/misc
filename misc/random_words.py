"""Utility for retrieving random words."""

import random
from argparse import ArgumentParser, ArgumentTypeError
from itertools import groupby
from pathlib import Path
from typing import Iterator

DEFAULT_WORDLIST = Path(__file__).parent / "words.txt"
DEFAULT_COUNT = 5


def iterchars(path: Path, encoding="utf-8") -> Iterator[str]:
    """Unicode-safe iterator over characters contained in the given file."""

    file = path.open()
    while char := file.read(1):
        while True:
            try:
                yield char.decode(encoding)
            except UnicodeDecodeError:
                char += file.read(1)
            else:
                break


def iterwords(path: Path, sep: str = " ,\n.:;()[]{}|<>-?!", **kwargs) -> Iterator[str]:
    """Iterator over words contained in the given file. kwargs are forwarded to iterchars."""

    return (
        word
        for word in (
            "".join(g[1])
            for g in groupby(iterchars(path, **kwargs), key=lambda ch: ch in sep)
        )
        if all(ch not in sep for ch in word)
    )


def random_words(
    n: int = DEFAULT_COUNT, path: Path = DEFAULT_WORDLIST, **kwargs
) -> list[str]:
    """Return n random words from the given file. kwargs are forwarded to iterwords."""

    return random.choices(set(iterwords(path, **kwargs)), k=n)


def file_path(strpath: str) -> Path:
    """Convert the passed str to a Path object and verify that it is an extant file."""

    path = Path(strpath)
    if not path.exists() or path.is_dir():
        raise ArgumentTypeError(f"Invalid wordlist: {strpath}")
    return path


def main():
    parser = ArgumentParser()
    parser.add_argument("n", type=int, nargs="?", default=DEFAULT_COUNT)
    parser.add_argument("-w", "--wordlist", type=file_path, default=DEFAULT_WORDLIST)
    args = parser.parse_args()
    words = random_words(args.n, args.wordlist)
    print(words)


if __name__ == "__main__":
    main()
