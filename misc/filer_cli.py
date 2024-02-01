from pathlib import Path
from typing import Literal

import cyclopts

from .filer import filer, HiddenFileFilter

cli = cyclopts.App()


@cli.default()
def explore(
    wd: Path = Path.cwd(),
    sort_by: Literal["name", "created", "accesed", "modified", "size"] = "name",
    sort_order: Literal["ascending", "descending"] = "ascending",
    show_hidden: bool = False,
):
    print(*(
        f'"{path}"' for path in
        filer(
        path=wd,
        sort_by=sort_by,
        sort_order=sort_order,
        filters=set() if show_hidden else {HiddenFileFilter()},
    )))
