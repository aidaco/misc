from inspect import signature
import sys
from typing import Iterable

from pydantic import TypeAdapter
from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Header, Footer
from textual.containers import VerticalScroll, Horizontal


class DictApp(App):
    CSS = """
    Screen {
        align: center top;
        width: 100%;
        height: auto;
    }
    ScrollableContainer {
        width: 100%;
        height: auto;
    }
    Horizontal {
        width: 100%;
        height: auto;
        min-height: 1;
    }
    Label {
        dock: left;
    }
    Input {
        dock: right;
        min-height: 1;
        min-width: 1;
        width: auto;
        height: auto;
        border: none;
    }
    Button {
        width: auto;
        background: green;
    }
    """
    BINDINGS = [
        ("ctrl+s", "submit", "Submit"),
    ]

    def __init__(self, prompt: str, names: Iterable[str]):
        super().__init__()
        self.title = prompt
        self.value = {name: "" for name in names}

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            for name in self.value:
                with Horizontal():
                    yield Label(name)
                    yield Input(id=name, select_on_focus=False)
        yield Footer()

    def on_mount(self) -> None:
        self.set_focus(self.query("Input").first())

    def on_input_changed(self, message):
        self.value[message.input.id] = message.value

    def action_submit(self) -> None:
        self.exit(self.value)


def forminput(prompt: str, fields: Iterable[str]) -> dict[str, str]:
    result = DictApp(prompt, fields).run(inline=True)
    if result is None:
        raise KeyboardInterrupt("User aborted forminput.")
    return result


def modelinput[T](
    prompt: str, model: type[T], typeadapter_cache: dict[type[T], TypeAdapter[T]] = {}
) -> T:
    ta = typeadapter_cache.get(model, None)
    if ta is None:
        ta = typeadapter_cache[model] = TypeAdapter(model)
    data = forminput(prompt, signature(model).parameters)
    return ta.validate_python(data)


if __name__ == "__main__":
    fields = sys.argv[1:] or input("Comma separated fields: ").split(",")
    result = forminput("Complete this form...", fields)
    print(result)
