from pathlib import Path
import sys
import shutil
from math import floor, ceil

from rich import box
from rich.text import Text 
from rich.console import Group, ConsoleOptions, Console
from rich.panel import Panel
from rich.table import Table, Column
from rich.measure import Measurement

from twidge.core import Dispatcher, RunBuilder
from twidge.widgets import EditString, Close


class Filer:
    run = RunBuilder()

    def __init__(self):
        self.panes: list[Pane] = []
        self.cursor: int = 0

    @property
    def focused(self):
        return self.panes[self.cursor]

    def set(self, wd: Path):
        self.panes = [Pane(self)]
        self.focused.set(wd)
        self.focused.focus()
        return self

    def cursor_left(self):
        if self.cursor > 0:
            self.focused.blur()
            self.cursor -= 1
            self.focused.focus()

    def cursor_right(self):
        if self.panes and self.cursor < len(self.panes) - 1:
            self.focused.blur()
            self.cursor += 1
            self.focused.focus()

    def open_pane_right(self, wd: Path):
        pane = Pane(self)
        self.panes.append(pane)
        pane.set(wd)

    def close_panes_right(self):
        if self.cursor < len(self.panes) - 1:
            self.panes = self.panes[:self.cursor+1]

    def close(self):
        sys.exit(0)

    def dispatch(self, event):
        self.focused.dispatch(event)

    def __rich__(self):
        t = Table(
            *(Column() for _ in self.panes),
            padding=0, pad_edge=False, show_header=False, show_edge=False, box=None
        )
        t.add_row(*self.panes)
        return t


class Pane:
    def __init__(self, filer: Filer):
        self.filer = filer
        self.dispatch = Dispatcher()
        self.cursor = 0
        self.focused = False
        self.views = []

    def set(self, wd: Path):
        paths = sorted(wd.iterdir())
        self.views = [View(path) for path in paths]
        self.selection_mode()
        self.selected.select()
        self.open_panes_right()
        return self

    @property
    def selected(self):
        return self.views[self.cursor]

    def selection_mode(self):
        self.dispatch.table = {
            'q': self.filer.close,
            'up': self.cursor_up,
            'k': self.cursor_up,
            'down': self.cursor_down,
            'j': self.cursor_down,
            'left': self.filer.cursor_left,
            'h': self.filer.cursor_left,
            'right': self.filer.cursor_right,
            'l': self.filer.cursor_right,
            'd': self.delete,
            'r': self.rename,
            'focus': self.focus,
            'blur': self.blur,
        }
        self.dispatch.default = lambda event: None

    def focus(self):
        self.focused = True
        for view in self.views:
            view.focus()

    def blur(self):
        self.focused = False
        for view in self.views:
            view.blur()

    def open_panes_right(self):
        if self.views and self.selected.path.is_dir() and len(list(self.selected.path.iterdir())) > 0:
            self.filer.open_pane_right(self.selected.path)

    def close_panes_right(self):
        self.filer.close_panes_right()

    def cursor_up(self):
        if not self.views:
            return
        self.close_panes_right()
        self.selected.deselect()
        self.cursor -= 1
        self.cursor %= len(self.views)
        self.selected.select()
        self.open_panes_right()

    def cursor_down(self):
        if not self.views:
            return
        self.close_panes_right()
        self.selected.deselect()
        self.cursor += 1
        self.cursor %= len(self.views)
        self.selected.select()
        self.open_panes_right()

    def rename(self):
        i = self.cursor
        view = self.selected
        rename = Rename(view.path)
        self.views[i] = rename

        def reset():
            self.views[i] = view
            self.open_panes_right()
            self.selection_mode()

        def do_rename():
            view.path = view.path.rename(view.path.with_name(rename.editor.result))
            self.close_panes_right()
            reset()

        self.dispatch.table = {
            'escape': reset,
            'enter': do_rename,
        }
        self.dispatch.default = rename.dispatch

    def delete(self):
        i = self.cursor
        path = self.selected.path
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        self.close_panes_right()
        self.selected.deselect()
        self.views.pop(i)
        if self.cursor == len(self.views):
            self.cursor -= 1
        if self.views:
            self.selected.select()
            self.open_panes_right()

    def __rich_measure__(self, console: Console, options: ConsoleOptions):
        width = max(len(v.path.name)+2 for v in _scrollview(self.views, self.cursor, options.max_height))
        return Measurement(width, width)

    def __rich_console__(self, console: Console, options: ConsoleOptions):
        color = 'green' if self.focused else 'white'
        widgets = _scrollview(self.views, self.cursor, options.max_height)
        yield Panel.fit(Group(*widgets), box=box.HEAVY, border_style=color, padding=0)


class View:
    def __init__(self, path: Path, color='bright_green'):
        self.color = color
        self.path = path
        self.focused = False
        self.selected = False

    def focus(self):
        self.focused = True

    def blur(self):
        self.focused = False

    def select(self):
        self.selected = True

    def deselect(self):
        self.selected = False

    def __rich__(self):
        fg, bg = self.color if self.focused else 'bright_white', 'black'
        if self.selected:
            fg, bg = bg, fg
        return Text(self.path.name, style=f'{fg} on {bg}')


class Rename:
    def __init__(self, path: Path):
        self.path = path
        self.editor = EditString(path.name)
        self.dispatch = self.editor.dispatch
        self.__rich__ = self.editor.__rich__


def _scrollview(widgets: list, center: int, height: int):
    height -= 1
    lstart = len(widgets[:center])
    lend = len(widgets[center:])
    ostart = ceil(height / 2)
    oend = ceil(height / 2)
    istart = max(0, center - ostart)
    iend = min(center + oend - 1, len(widgets))
    return widgets[istart:iend]


if __name__ == '__main__':
    if len(sys.argv) > 1 and (wd := sys.argv[1]):
        path = Path(wd)
    else:
        path = Path.cwd()
    Filer().set(path).run()
