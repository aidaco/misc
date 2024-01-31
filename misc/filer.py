from pathlib import Path
import shutil
from math import ceil
from dataclasses import dataclass, field
from operator import attrgetter
from typing import Any, Callable, ClassVar, Literal, Protocol, ForwardRef
import time
import stat
from itertools import chain, pairwise, islice
from types import NoneType
from threading import Thread

from rich.measure import Measurement
from rich.text import Text
from rich.console import Group, ConsoleOptions, Console, RenderableType
from rich.table import Table, Column
from rich.style import Style

from twidge.core import RunBuilder, Event, HandlerType, Dispatcher, StrEvent
from twidge.widgets import EditString, Close


@dataclass
class StackView[T: RenderableType]:
    stack: list[T]

    def __rich__(self) -> RenderableType:
        table = Table(
            *(Column() for _ in self.stack),
            padding=(0, 1),
            collapse_padding=True,
            pad_edge=False,
            show_header=False,
            show_edge=False,
        )
        table.add_row(*self.stack)
        return table


@dataclass
class OffsetScroller[T: RenderableType]:
    views: list[T]
    offset: int

    def __rich_measure__(self, console: Console, options: ConsoleOptions):
        if not self.views:
            return Measurement(0, 0)
        m = max(*(console.measure(v) for v in self.views))
        if isinstance(m, int):
            return Measurement(m, m)
        return m

    def __rich_console__(self, console: Console, options: ConsoleOptions):
        if not self.views:
            yield Text("")
        height = options.max_height - 1
        center = self.offset
        ostart = ceil(height / 2)
        oend = ceil(height / 2)
        istart = max(0, center - ostart)
        iend = min(center + oend - 1, len(self.views))
        dstart = ostart - len(self.views[istart:center])
        dend = oend - len(self.views[center:iend])
        fstart = max(0, istart - dend)
        fend = min(len(self.views), iend + dstart)
        yield Group(*self.views[fstart:fend])


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


def focused_text(text: Text) -> Text:
    text.stylize(Style(color="black", bgcolor="bright_white"))
    return text


@dataclass
class PathView:
    path: Path
    state: dict[str, NoneType] = field(default_factory=dict)
    state_format: ClassVar[dict[str, Callable[[Text], Text]]] = {
        "focused": focused_text,
        "selected": lambda text: Text(
            ">", style=Style(color="bright_yellow", blink=True)
        )
        + text
        + Text("<", style=Style(color="bright_yellow", blink=True)),
    }

    def add_state(self, state: str):
        self.state[state] = None

    def remove_state(self, state: str):
        self.state.pop(state, None)

    def __rich__(self) -> RenderableType:
        text = Text(self.path.name)
        for state in self.state:
            text = self.state_format[state](text)
        return text


@dataclass
class DirectoryView:
    paths: list[Path]
    pathviews: list[PathView] = field(default_factory=list)
    view: OffsetScroller = field(init=False)

    def __post_init__(self):
        self.pathviews = []
        self.view = OffsetScroller(self.pathviews, 0)
        self.reload()

    def reload(self):
        self.pathviews.clear()
        self.pathviews.extend(PathView(path) for path in self.paths)

    def __rich__(self) -> RenderableType:
        return self.view


@dataclass
class PathAnalyser:
    path: Path
    parts: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.reload()

    def reload(self):
        self.parts.append(f"Owner: {self.path.owner()}:{self.path.group()}")
        st = self.path.stat()
        self.parts.append(f"Mode: {stat.filemode(st.st_mode)}")
        self.parts.append(f"Size: {humanize_bytes(st.st_size)}")
        if self.path.is_symlink():
            self.parts.append(f"Link to: {self.path.readlink()}")

    def stop(self):
        pass

    def __rich__(self):
        return Group(*self.parts)


@dataclass
class DirectoryAnalyser:
    path: Path
    file_count: int = 0
    directory_count: int = 0
    total_size: int = 0
    file_types: set[str] = field(default_factory=set)
    running: bool = True

    def __post_init__(self):
        Thread(target=self.analyse).start()

    def analyse(self):
        for path, directories, files in self.path.walk():
            if not self.running:
                return
            self.directory_count += len(directories)
            self.file_count += len(files)
            for file in files:
                file = path / file
                self.file_types.add(file.suffix.lstrip("."))
                try:
                    self.total_size += file.stat().st_size
                except IOError:
                    ...
        self.running = False

    def stop(self):
        self.running = False

    def __rich__(self):
        return Group(
            f"Files: {self.file_count}",
            f"Directories: {self.directory_count}",
            f"Total Size: {humanize_bytes(self.total_size)}",
            f'File Types: [{", ".join(self.file_types)}]',
        )


class Analyser(Protocol):
    def __rich__(self) -> RenderableType:
        ...

    def stop(self):
        ...


@dataclass
class PathPreview:
    select: "Select"
    sort: PathSort
    parts: list[Analyser] = field(default_factory=list)

    def __post_init__(self):
        self.reload()

    def reload(self):
        for part in self.parts:
            part.stop()
        self.parts.clear()
        if self.select.focused:
            path = self.select.focused
            self.parts.append(PathAnalyser(path))
            if path.is_file():
                ...
            elif path.is_dir():
                self.parts.append(DirectoryAnalyser(path))

    def __rich__(self):
        return Group(*self.parts)


@dataclass
class ParentsView:
    select: "Select"
    sort: PathSort
    directoryviews: list[DirectoryView] = field(init=False)
    view: RenderableType = field(init=False)

    def __post_init__(self):
        self.directoryviews = []
        self.view = StackView(self.directoryviews)
        self.reload()

    def reload(self):
        self.directoryviews.clear()
        root = self.select.path
        path_info = pairwise(chain(reversed(list(root.parents)[:2]), [root]))
        for path, selected in path_info:
            paths = self.sort(path.iterdir())
            view = DirectoryView(paths)
            try:
                ix = paths.index(selected)
            except ValueError:
                ix = 0
            view.pathviews[ix].add_state("focused")
            self.directoryviews.append(view)

    def __rich__(self):
        return self.view


@dataclass
class Select:
    path: Path
    sort: PathSort
    cursor: int = 0
    selection: set[Path] = field(default_factory=set)
    paths: list[Path] = field(default_factory=list)
    parentview: ParentsView = field(init=False)
    currentview: DirectoryView = field(init=False)
    preview: PathPreview = field(init=False)
    parts: list = field(default_factory=list)
    view: RenderableType = field(init=False)

    @property
    def focused(self):
        try:
            return self.paths[self.cursor]
        except IndexError:
            self.cursor = max(0, len(self.paths) - 1)
            if not self.paths:
                return None
            return self.paths[self.cursor]

    def __post_init__(self):
        self.currentview = DirectoryView(self.paths)
        self.parentview = ParentsView(self, self.sort)
        self.preview = PathPreview(self, self.sort)
        self.parts = [self.parentview, self.currentview, self.preview]
        self.view = StackView(self.parts)
        self.reload_paths()
        self.reload()

    def reload_paths(self):
        self.paths.clear()
        self.paths.extend(self.sort(self.path.iterdir()))

    def reload(self):
        self.currentview.reload()
        self.parentview.reload()
        self.preview.reload()
        if self.focused:
            self.currentview.pathviews[self.cursor].add_state("focused")
        for pv in self.currentview.pathviews:
            if pv.path in self.selection:
                pv.add_state("selected")
        for dv in self.parentview.directoryviews:
            for pv in dv.pathviews:
                if pv.path in self.selection:
                    pv.add_state("selected")

    def toggle_select_focused(self):
        if self.focused:
            path = self.focused
            if path in self.selection:
                self.selection.remove(path)
                self.currentview.pathviews[self.cursor].remove_state("selected")
            else:
                self.selection.add(path)
                self.currentview.pathviews[self.cursor].add_state("selected")

    def cursor_bottom(self):
        self.currentview.pathviews[self.cursor].remove_state("focused")
        self.cursor = 0
        self.currentview.pathviews[self.cursor].add_state("focused")
        self.preview.reload()

    def cursor_top(self):
        self.currentview.pathviews[self.cursor].remove_state("focused")
        self.cursor = len(self.currentview.pathviews) - 1
        self.currentview.view.offset = self.cursor
        self.currentview.pathviews[self.cursor].add_state("focused")
        self.preview.reload()

    def cursor_down(self):
        self.currentview.pathviews[self.cursor].remove_state("focused")
        self.cursor = min(len(self.currentview.pathviews) - 1, self.cursor + 1)
        self.currentview.view.offset = self.cursor
        self.currentview.pathviews[self.cursor].add_state("focused")
        self.preview.reload()

    def cursor_up(self):
        self.currentview.pathviews[self.cursor].remove_state("focused")
        self.cursor = max(0, self.cursor - 1)
        self.currentview.view.offset = self.cursor
        self.currentview.pathviews[self.cursor].add_state("focused")
        self.preview.reload()

    def cursor_left(self):
        current = self.path
        self.path = self.path.parent
        self.reload_paths()
        try:
            self.cursor = self.paths.index(current)
            self.currentview.view.offset = self.cursor
        except ValueError:
            ...
        self.reload()
        self.preview.reload()

    def cursor_right(self):
        if self.focused:
            path = self.focused
            if not path.is_dir():
                return
            self.path = path
            self.cursor = 0
            self.currentview.view.offset = self.cursor
            self.reload_paths()
            self.reload()
            self.preview.reload()
            self.parentview.reload()

    @property
    def result(self):
        return self.selection

    def __rich__(self):
        return self.view


@dataclass
class RenameView:
    select: Select
    path: Path | None = None
    editor: EditString = field(init=False)

    def __post_init__(self):
        self.next_path()
        self.reload()

    def next_path(self):
        try:
            self.path = self.select.selection.pop()
            self.reload()
        except KeyError:
            self.path = None
            self.select.reload_paths()
            self.select.reload()

    def reload(self):
        if self.path is None:
            return
        self.editor = EditString(self.path.name)
        self.select.path = self.path
        if self.path.is_dir():
            self.select.path = self.path
            self.select.reload_paths()
        else:
            self.select.path = self.path.parent
            self.select.reload_paths()
            self.select.cursor = self.select.paths.index(self.path)
        self.select.reload()
        self.select.currentview.pathviews[self.select.cursor] = self.editor

    def rename(self):
        path = self.path.rename(self.path.with_name(self.editor.result))
        if path.is_dir():
            for sub in self.select.selection.copy():
                if sub.is_relative_to(path):
                    self.select.selection.discard(sub)

    def __rich__(self):
        return self.select


class Widget(Protocol):
    def dispatch(self, event: Event):
        ...

    def __rich__(self) -> RenderableType:
        ...


@dataclass
class Explorer:
    cwd: Path
    sort: PathSort
    select: Select = field(init=False)
    view: RenderableType = field(init=False)

    run: ClassVar = RunBuilder()

    def __post_init__(self):
        self.select = Select(self.cwd, self.sort)
        self.dispatch = Dispatcher()
        self.select_mode()

    def delete_selection(self) -> None:
        if not self.select.selection:
            return
        for path in self.select.selection:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            elif path.is_file():
                path.unlink(missing_ok=True)
        self.select.selection.clear()
        self.select.reload_paths()
        self.select.reload()

    def rename_selection(self):
        if not self.select.selection:
            return

        rename = RenameView(self.select)

        def do_rename():
            rename.rename()
            if not self.select.selection:
                self.select_mode()
            rename.next_path()
            rename.reload()

        def cancel_rename():
            if not self.select.selection:
                self.select_mode()
            rename.next_path()
            rename.reload()

        self.dispatch.replace(
            table={
                StrEvent("enter"): do_rename,
                StrEvent("escape"): cancel_rename,
            },
            default=lambda e: rename.editor.dispatch(e),
        )
        self.view = rename

    def copy_selection(self):
        def do_copy():
            dest = self.select.path
            for src in self.select.selection:
                if src.is_dir():
                    shutil.copytree(src, dest)
                else:
                    shutil.copy2(src, dest)
            time.sleep(1)
            self.select.selection.clear()
            self.select.reload_paths()
            self.select_mode()

        def cancel_copy():
            self.select_mode()

        self.dispatch.replace(
            table={
                "g": self.select.cursor_top,
                "G": self.select.cursor_bottom,
                "h": self.select.cursor_left,
                "j": self.select.cursor_down,
                "k": self.select.cursor_up,
                "l": self.select.cursor_right,
                "v": do_copy,
                "escape": cancel_copy,
            },
            default=None,
        )

    def select_mode(self):
        self.view = self.select
        self.dispatch.replace(
            table={
                StrEvent("g"): self.select.cursor_top,
                StrEvent("G"): self.select.cursor_bottom,
                StrEvent("h"): self.select.cursor_left,
                StrEvent("j"): self.select.cursor_down,
                StrEvent("k"): self.select.cursor_up,
                StrEvent("l"): self.select.cursor_right,
                StrEvent("space"): self.select.toggle_select_focused,
                StrEvent("d"): self.delete_selection,
                StrEvent("r"): self.rename_selection,
                StrEvent("c"): self.copy_selection,
            },
            default=lambda e: None,
        )

    @property
    def result(self):
        return self.select.selection

    def __rich__(self):
        return self.view


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


def filer(
    path: Path = Path.cwd(),
    sort_by: Literal["name", "created", "accesed", "modified", "size"] = "name",
    sort_order: Literal["ascending", "descending"] = "ascending",
    filters: set[Callable[[Path], bool]] = {HiddenFileFilter()},
):
    return Close(Explorer(path, PathSort(sort_by, sort_order, filters=filters))).run()
