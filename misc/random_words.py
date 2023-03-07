"""Utility for retrieving random words."""

import random
from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path

DEFAULT_WORDLIST = Path(__file__).parent / "words.txt"
DEFAULT_COUNT = 5


def iterwords(path: Path, sep: str = " ,\n.:;()[]{}|<>-?!"):
    sep = set(sep)
    with path.open() as file:
        word = ""
        while (ch := file.read(1)) != "":
            if ch not in sep:
                word += sep
            else:
                if word:
                    yield word
                    word = ""
        if word:
            yield word


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
