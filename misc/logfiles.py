"""Brief fun with rich's logging features. Walks through files and logs their names.

Aidan Courtney, 2021."""

import time
from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path

from rich.console import Console


def logtree(console: Console, start: Path, rate: int = 50):
    """Log the contents of start and its children to the console at the given rate (items/second)."""

    def _log_dir(target: Path, depth: int = 0):
        for path in target.iterdir():
            name = (
                f"[red]{path.name}[/red]/"
                if path.is_dir()
                else f"[green]{path.name}[/green]"
            )
            console.log("  " * depth, name)
            time.sleep(1 / rate)
            if path.is_dir():
                _log_dir(path, depth + 1)

    return _log_dir(start)


def file_path(strpath: str) -> Path:
    """Convert the passed str to a Path object and verify that it is an extant file."""

    path = Path(strpath)
    if not path.exists() or path.is_dir():
        raise ArgumentTypeError(f"Invalid wordlist: {strpath}")
    return path


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("path", type=file_path, nargs="?", default=Path.cwd())
    console = Console(log_path=False)
    logtree(console, parser.parse_args().path)
