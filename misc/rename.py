from pathlib import Path
import shutil

from twidge.widgets import Close, FocusGroup, EditString

import typer

cli = typer.Typer()

def _check_exist(path):
    if not path.exists():
        raise ValueError(f'Not found: {path}.')
    return True

def _check_no_overwrite(path, force):
    if path.exists() and not force:
        raise ValueError(f'Would overwrite: {path}.')
    return True

def _check_parents(path):
    path.parent.mkdir(parents=True)

def _edititer(it):
    editors = (EditString(s) for s in it)
    return Close(FocusGroup(*editors)).run()

@cli.command()
def rename(files: list[str], force: bool = False):
    paths = ((Path(old), Path(new)) for old, new in zip(files, _edititer(files)) if old != new)
    paths = ((old, new) for old, new in paths if _check_exist(old) and _check_no_overwrite(new, force))
    for old, new in paths:
        old.rename(new)
        print(f'[{old}] -> [{new}]')

if __name__ == '__main__':
    cli()

            

