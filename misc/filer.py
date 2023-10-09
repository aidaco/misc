from pathlib import Path
import sys
import shutil

from rich.text import Text 
from rich.console import Group 

from twidge.core import Dispatcher
from twidge.widgets import EditString, Close


class Filer:
    def __init__(self, *paths: Path):
        self.dispatch = Dispatcher()
        self.paths = list(paths)
        self.widgets = [View(p) for p in self.paths]
        self.cursor = 0
        if self.widgets:
            self.widgets[self.cursor].dispatch('focus')
        self.selection_mode()

    def selection_mode(self):
        self.dispatch.table = {
            'up': self.cursor_up,
            'k': self.cursor_up,
            'down': self.cursor_down,
            'j': self.cursor_down,
            'd': self.delete,
            'r': self.rename,
        }
        self.dispatch.default = lambda event: None

    def rename(self):
        i = self.cursor
        path = self.paths[i]
        rename = Rename(path)
        self.widgets[i] = rename

        def do_rename():
            name = path.with_name(rename.editor.result)
            new = path.rename(name)
            self.paths[i] = new
            self.widgets[i] = View(new)
            self.widgets[i].dispatch('focus')
            self.selection_mode()

        self.dispatch.table = {
            'enter': do_rename,
        }
        self.dispatch.default = rename.dispatch

    def cursor_up(self):
        if not self.paths:
            return
        self.widgets[self.cursor].dispatch('blur')
        self.cursor -= 1
        self.cursor %= len(self.paths)
        self.widgets[self.cursor].dispatch('focus')

    def cursor_down(self):
        if not self.paths:
            return
        self.widgets[self.cursor].dispatch('blur')
        self.cursor += 1
        self.cursor %= len(self.paths)
        self.widgets[self.cursor].dispatch('focus')

    def delete(self):
        i = self.cursor
        p = self.paths[i]
        if p.is_dir():
            shutil.rmtree(p)
            return
        p.unlink()
        self.paths.pop(i)
        self.widgets[self.cursor].dispatch('blur')
        self.widgets.pop(i)
        if self.cursor >= len(self.widgets):
            self.cursor -= 1
        if self.widgets:
            self.widgets[self.cursor].dispatch('focus')

    def __rich__(self):
        return Group(
            Text.from_markup('[green underline]Filer[/]'),
            *self.widgets
        )


class View:
    def __init__(self, path: Path):
        self.path = path
        self.focused = False

    def dispatch(self, event):
        match event:
            case 'focus':
                self.focused = True
            case 'blur':
                self.focused = False

    def __rich__(self):
        if self.focused:
            return Text.from_markup(f'[black on white]{self.path.name}[/]')
        return str(self.path.name)


class Rename:
    def __init__(self, path: Path):
        self.path = path
        self.editor = EditString(path.name)
        self.dispatch = self.editor.dispatch
        self.__rich__ = self.editor.__rich__


if __name__ == '__main__':
    Close(Filer(*(Path(arg) for arg in sys.argv[1:]))).run()
