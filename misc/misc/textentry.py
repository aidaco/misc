from rich import print
from rich.align import Align
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
from textual.app import App
from textual.reactive import Reactive
from textual.widget import Widget
from textual.widgets import Placeholder


class TextEntry(Widget):
    cursor = Reactive(0)
    text = Reactive("")
    focused = Reactive(False)

    def render(self) -> Panel:
        content = self.text + " "
        text = (
            content
            if not self.focused
            else (
                content[: self.cursor]
                + "[black on white]"
                + content[self.cursor]
                + "[/]"
                + content[self.cursor + 1 :]
            )
        )
        return Panel.fit(
            text,
            title=f"{self.name} {self.cursor}",
            title_align="left",
            border_style="yellow" if self.focused else "bright_blue",
        )

    def on_focus(self) -> None:
        self.focused = True

    def on_blur(self) -> None:
        self.focused = False

    def cursor_left(self):
        if self.cursor != 0:
            self.cursor -= 1
            if self.text[self.cursor] == "\n":
                self.cursor -= 1

    def cursor_right(self):
        if self.cursor < len(self.text):
            self.cursor += 1
            if self.cursor < len(self.text) and self.text[self.cursor] == "\n":
                self.cursor += 1

    def next_word(self):
        next_space = self.text[self.cursor :].find(" ")
        if next_space == -1:
            return len(self.text)
        else:
            return self.cursor + next_space + 1

    def prev_word(self):
        prev_space = self.text[: self.cursor - 1][::-1].find(" ")
        if prev_space == -1:
            return 0
        else:
            return self.cursor - prev_space - 1

    def delete_word(self):
        n = self.prev_word()
        self.text = self.text[:n] + self.text[self.cursor :]
        self.cursor = n

    def insert(self, char: str):
        self.text = self.text[: self.cursor] + char + self.text[self.cursor :]
        self.cursor += 1

    def backspace(self):
        if self.cursor != 0:
            self.text = self.text[: self.cursor - 1] + self.text[self.cursor :]
            self.cursor -= 1

    def on_key(self, event):
        match event.key:
            case "enter":
                self.insert("\n")
            case "ctrl+h":
                self.backspace()
            case "ctrl+i":
                self.app.focus_next()
            case "shift+tab":
                self.app.focus_prev()
            case "left":
                self.cursor_left()
            case "right":
                self.cursor_right()
            case "ctrl+delete":
                self.delete_word()
            case "ctrl+left":
                self.cursor = self.prev_word()
            case "ctrl+right":
                self.cursor = self.next_word()
            case str(x) if len(x) == 1:  # Limit to single characters
                self.insert(x)


class DictEntry(App):
    focus = Reactive(0)

    def __init__(self, fields: list[str], set_result, **kwargs):
        self.set_result = set_result
        self.fields = fields
        super().__init__(**kwargs)

    async def on_load(self) -> None:
        await self.bind("escape", "quit", "Quit")
        self.entries = [TextEntry(field) for field in self.fields]

    async def on_mount(self) -> None:
        grid = await self.view.dock_grid(edge="bottom", name="left")
        grid.add_column("left", fraction=1)
        for n in range(len(self.entries)):
            grid.add_row(str(n), fraction=1)

        grid.place(*self.entries)
        self.focus = 0

    async def action_quit(self) -> None:
        self.set_result({k: w.text for k, w in zip(self.fields, self.entries)})
        await super().action_quit()

    def focus_next(self) -> None:
        self.focus = (self.focus + 1) % len(self.entries)

    def focus_prev(self) -> None:
        self.focus = (self.focus - 1) % len(self.entries)

    async def watch_focus(self, x) -> None:
        await self.set_focus(self.entries[self.focus])


def dictin(*fields: str) -> dict[str, str]:
    result = {}

    def set_result(value: dict[str, str]):
        nonlocal result
        result = value

    DictEntry.run(fields=fields, set_result=set_result)

    return result


if __name__ == "__main__":
    result = dictin("name", "email", "phone", "address")
    print(result)
