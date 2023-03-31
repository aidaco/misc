"""Tree view of the namespace in a python package."""

import ast
from functools import partial
from pathlib import Path
from types import MethodType

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table

app = typer.Typer()


@app.command()
def tree(cwd: Path = Path.cwd()):
    Console().print(_RichView(_tree, cwd))


class _RichView:
    def __init__(self, fn, *args, **kwargs):
        self.fn = fn
        self.args, self.kwargs = args, kwargs

    def __rich_console__(self, console, options):
        yield from self.fn(*self.args, **self.kwargs)


def _tree(cwd: Path = Path.cwd()):
    for file in Path(cwd).iterdir():
        if file.name.startswith(".") or file.name.startswith("_"):
            continue
        elif file.is_dir() and next(file.iterdir(), None):
            yield _display(f"[bold white]{file.name}[/]", lines=_tree(file), dark=False)
        elif file.suffix == ".py":
            yield _display(f"[bold white]{file.name}[/]", lines=_getdefines(file))


def _getdefines(pyfile: Path) -> list:
    for node in ast.parse(pyfile.read_text()).body:
        match node:
            case ast.Assign():
                yield "[blue],[/] ".join(
                    f"[yellow]{t.id}[/]"
                    for t in node.targets
                    if isinstance(t, ast.Name)
                )
            case ast.FunctionDef():
                yield f"[cyan]def[/] [yellow]{node.name}[/]"
            case ast.ClassDef():
                yield f"[magenta]class[/] [yellow]{node.name}[/]"
            case ast.Import():
                yield f'[green]import[/] [yellow]{", ".join(a.name for a in node.names)}[/]'
            case ast.ImportFrom():
                yield f"""[blue]from[/] [yellow]{node.module}[/] [blue]import[/] {"[blue],[/] ".join(f"[yellow]{alias.name}[/]{f' [blue]as[/] [yellow]{alias.asname}[/]' if alias.asname else ''}" for alias in node.names)}"""


def _display(file: str | None = None, lines: list[str] | None = [], dark: bool = True):
    color = "rgb(250,50,200)" if not dark else "rgb(240,170,225)"
    return Panel.fit(Group(*lines), title=file, border_style=color)


if __name__ == "__main__":
    app()
