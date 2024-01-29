from pathlib import Path
import sys
import shutil
from math import ceil
from dataclasses import dataclass, field
from operator import attrgetter
from typing import Any, Callable, ClassVar, Literal
import os
import stat
from itertools import chain, pairwise
from rich.measure import Measurement

from rich.text import Text
from rich.console import Group, ConsoleOptions, Console, RenderableType
from rich.table import Table, Column
from rich.style import StyleType

from twidge.core import RunBuilder, Event, HandlerType
from twidge.widgets import EditString, Close


@dataclass
class PathSort:
    by: Literal["name", "created", "accesed", "modified", "size"] = "name"
    order: Literal["ascending", "descending"] = "ascending"
    filters: set[Callable[[Path], bool]] = field(default_factory=set)

    def keyfn(
        self,
        keyfns: dict[str, Callable[[Path], Any]] = {
            "name": attrgetter("name"),
            "created": lambda path: path.stat().st_ctime,
            "accessed": lambda path: path.stat().st_atime,
            "modified": lambda path: path.stat().st_mtime,
            "size": lambda path: path.stat().st_size,
        },
    ) -> Callable[[Path], Any]:
        return keyfns[self.by]

    def __call__(self, paths):
        paths = (
            path for path in paths if not any(filter(path) for filter in self.filters)
        )
        paths = sorted(paths, key=self.keyfn())
        return list(paths if self.order == "ascending" else reversed(paths))


class HiddenFileFilter:
    def __call__(self, path: Path):
        return path.name.startswith(".")


@dataclass
class PathView:
    path: Path
    style: StyleType

    def __rich__(self) -> RenderableType:
        return Text(self.path.name, style=self.style)


@dataclass
class StackView:
    stack: list[RenderableType]
    view: RenderableType = ""

    def __post_init__(self):
        self.reload()

    def reload(self):
        self.view = Table(
            *(Column() for _ in self.stack),
            padding=(0, 1),
            collapse_padding=True,
            pad_edge=False,
            show_header=False,
            show_edge=True,
        )
        self.view.add_row(*self.stack)

    def __rich__(self) -> RenderableType:
        return self.view


@dataclass
class OffsetScroller:
    views: list
    offset: int

    def __rich_measure__(self, console: Console, options: ConsoleOptions):
        m = max(*(console.measure(v) for v in self.views))
        if isinstance(m, int):
            return Measurement(m, m)
        return m

    def __rich_console__(self, console: Console, options: ConsoleOptions):
        widgets = _scrollview(self.views, self.offset, options.max_height)
        yield Group(*widgets)


@dataclass
class DirectoryView:
    paths: list[Path]
    scroll_offset: int
    selected: set[int] = field(default_factory=set)
    pathviews: list[PathView] = field(default_factory=list)
    view: RenderableType = field(init=False)

    def __post_init__(self):
        self.reload()

    def reload(self):
        self.pathviews = [
            PathView(
                path,
                "bright_white"
                if ix not in self.selected
                else "bright_black on bright_white",
            )
            for ix, path in enumerate(self.paths)
        ]
        self.view = OffsetScroller(self.pathviews, self.scroll_offset)

    def __rich__(self) -> RenderableType:
        return self.view


@dataclass
class PathPreview:
    path: Path
    stat: os.stat_result
    children: list[Path] | None = None

    def __rich__(self):
        parts: list[RenderableType] = [
            f"User: {self.path.owner()}",
            f"Group: {self.path.group()}",
            f"Mode: {stat.filemode(self.stat.st_mode)}",
            f"Size: {humanize_bytes(self.stat.st_size)}",
        ]
        if self.children is not None:
            parts.append(f"Items: {len(self.children)}")

        return Group(*parts)


@dataclass
class DirectoryStackSelectView:
    path: Path
    path_stat: os.stat_result
    path_contents: list[Path] | None
    parents: list[Path]
    parents_contents: list[list[Path]]
    directoryviews: list[DirectoryView] = field(init=False)
    preview: PathPreview = field(init=False)
    view: RenderableType = field(init=False)

    def __post_init__(self):
        self.reload()

    def reload(self):
        self.preview = PathPreview(self.path, self.path_stat, self.path_contents)
        path_info = zip(
            pairwise(chain(self.parents, [self.path])),
            self.parents_contents,
        )
        self.directoryviews = []
        for (path, selected), paths in path_info:
            try:
                ix = paths.index(selected)
            except ValueError:
                ix = 0
            view = DirectoryView(paths, ix, {ix})
            self.directoryviews.append(view)
        self.view = StackView([*self.directoryviews, self.preview])

    def __rich__(self):
        return self.view


@dataclass
class DirectoryStackRenameView:
    path: Path
    editor: EditString
    selectview: DirectoryStackSelectView

    def __post_init__(self):
        self.reload()

    def reload(self):
        ix = self.selectview.directoryviews[-1].paths.index(self.path)
        self.selectview.directoryviews[-1].pathviews[ix] = self.editor

    def __rich__(self):
        return self.selectview


def humanize_bytes(bytes, precision=1):
    abbrevs = (
        (1 << 50, "PB"),
        (1 << 40, "TB"),
        (1 << 30, "GB"),
        (1 << 20, "MB"),
        (1 << 10, "kB"),
    )
    factor, suffix = (1, "B")
    for factor, suffix in abbrevs:
        if bytes >= factor:
            break
    relbytes = bytes / factor
    return f"{relbytes:.{precision}f} {suffix}"


@dataclass
class SingleSelect:
    wd: Path
    sort: PathSort
    cursor: int = 0

    paths: list[Path] = field(init=False)
    view: DirectoryStackSelectView = field(init=False)

    def __post_init__(self):
        self.reload_paths()

    def clamp_cursor(self) -> None:
        self.cursor = max(0, min(self.cursor, len(self.paths) - 1))

    def reload_paths(self) -> None:
        self.paths = self.sort(self.wd.iterdir())
        self.clamp_cursor()
        self.reload_view()

    def reload_view(self) -> None:
        selection = self.selection
        if selection:
            parents = list(selection.parents)[:2][::-1]
            contents = [self.sort(path.iterdir()) for path in parents]
            self.view = DirectoryStackSelectView(
                selection,
                selection.stat(),
                list(selection.iterdir()) if selection.is_dir() else None,
                parents,
                contents,
            )

    @property
    def selection(self) -> Path | None:
        try:
            return self.paths[self.cursor]
        except IndexError:
            self.clamp_cursor()
        try:
            return self.paths[self.cursor]
        except IndexError:
            return None

    def cursor_top(self):
        self.cursor = 0
        self.reload_view()

    def cursor_bottom(self):
        self.cursor = len(self.paths) - 1
        self.reload_view()

    def cursor_down(self):
        self.cursor += 1
        self.clamp_cursor()
        self.reload_view()

    def cursor_up(self):
        self.cursor -= 1
        self.clamp_cursor()
        self.reload_view()

    def cursor_left(self):
        selection = self.wd
        self.wd = self.wd.parent
        self.reload_paths()
        try:
            self.cursor = self.paths.index(selection)
        except ValueError:
            ...
        self.reload_view()

    def delete_selection(self) -> None:
        path = self.selection
        if not path:
            return
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)
        self.reload_paths()

    def cursor_right(self):
        selection = self.selection
        if selection and selection.is_dir() and len(list(selection.iterdir())) > 0:
            self.wd = selection
            self.reload_paths()

    @property
    def result(self) -> Path | None:
        return self.selection

    def __rich__(self):
        return self.view


@dataclass
class SingleRename:
    path: Path
    selectview: DirectoryStackSelectView
    editor: EditString = field(init=False)
    view: DirectoryStackRenameView = field(init=False)

    def __post_init__(self):
        self.editor = EditString(self.path.name)
        self.reload()

    def reload(self) -> None:
        self.view = DirectoryStackRenameView(self.path, self.editor, self.selectview)

    def finish(self) -> None:
        self.path.rename(self.path.with_name(self.editor.result))
        self.selectview.reload()

    def __rich__(self):
        return self.view


@dataclass
class Mode:
    widget: Any | Callable[[], Any]
    table: dict[Event, HandlerType]
    default: Callable[[Event], None] | None = None

    def dispatch(self, event):
        handler = self.table.get(event, None)
        if handler:
            handler()
        elif self.default:
            self.default(event)


@dataclass
class ModeSwitch:
    modes: dict[str, Mode]
    mode: str

    run: ClassVar = RunBuilder()

    @property
    def widget(self):
        o = self.modes[self.mode].widget
        if not callable(o):
            return o
        else:
            return o()

    def set_mode(self, mode):
        self.mode = mode

    def dispatch(self, event: Event) -> None:
        self.modes[self.mode].dispatch(event)

    def __rich__(self):
        return self.widget

    @property
    def result(self):
        return self.widget.result


def filer(
    path: Path = Path.cwd(),
    sort_by: Literal["name", "created", "accesed", "modified", "size"] = "name",
    sort_order: Literal["ascending", "descending"] = "ascending",
    filters: set[Callable[[Path], bool]] = {HiddenFileFilter()}
):
    select = SingleSelect(path, PathSort(sort_by, sort_order, filters=filters))
    rename: SingleRename | None = None
    modeswitch: ModeSwitch = None  # type: ignore
    app: Close = None  # type: ignore
    copying: Path | None = None

    def start_rename():
        nonlocal rename
        if modeswitch.mode != "select" or not select.selection:
            return
        rename = SingleRename(select.selection, select.view)
        modeswitch.set_mode("rename")

    def dispatch_rename(event):
        if rename:
            rename.editor.dispatch(event)

    def cancel_rename():
        nonlocal rename
        if modeswitch.mode != "rename" or not rename:
            return
        rename = None
        select.reload_view()
        modeswitch.set_mode("select")

    def finish_rename():
        nonlocal rename
        if modeswitch.mode != "rename" or not rename:
            return

        rename.finish()
        rename = None
        select.reload_paths()
        modeswitch.set_mode("select")

    def start_copying():
        nonlocal copying
        if modeswitch.mode != "select" or not select.selection:
            return
        copying = select.selection
        print(f"{copying=}")
        modeswitch.set_mode("copying")

    def cancel_copying():
        nonlocal copying
        copying = None

    def finish_copying():
        nonlocal copying
        if modeswitch.mode != "copying" or not copying or not select.selection:
            return
        dest = (
            select.selection.parent if select.selection.is_file() else select.selection
        )
        shutil.copy2(copying, dest)
        print(f"{copying=} {dest}")
        copying = None
        select.reload_paths()
        modeswitch.set_mode("select")

    modeswitch = ModeSwitch(
        modes={
            "select": Mode(
                select,
                {
                    "g": select.cursor_top,
                    "G": select.cursor_bottom,
                    "h": select.cursor_left,
                    "j": select.cursor_down,
                    "k": select.cursor_up,
                    "l": select.cursor_right,
                    "d": select.delete_selection,
                    "c": start_copying,
                    "q": lambda: app.run.stop(),
                    "r": start_rename,
                },
            ),
            "rename": Mode(
                lambda: rename,
                {
                    "enter": finish_rename,
                    "escape": cancel_rename,
                },
                dispatch_rename,
            ),
            "copying": Mode(
                select,
                {
                    "g": select.cursor_top,
                    "G": select.cursor_bottom,
                    "h": select.cursor_left,
                    "j": select.cursor_down,
                    "k": select.cursor_up,
                    "l": select.cursor_right,
                    "q": lambda: app.run.stop(),
                    "v": finish_copying,
                    "escape": cancel_copying,
                },
            ),
        },
        mode="select",
    )
    app = Close(modeswitch)
    return app.run()


def _scrollview(widgets: list, center: int, height: int):
    height -= 1
    ostart = ceil(height / 2)
    oend = ceil(height / 2)
    istart = max(0, center - ostart)
    iend = min(center + oend - 1, len(widgets))
    return widgets[istart:iend]
