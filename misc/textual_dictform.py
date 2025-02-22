from textual.app import App, ComposeResult
from textual.widgets import Input, Label, Footer
from textual.containers import ScrollableContainer, Horizontal


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
    BINDINGS = [('ctrl+s', 'submit', 'Submit')]

    def __init__(self, *names: str):
        self.value = {name: '' for name in names}
        super().__init__()

    def compose(self) -> ComposeResult:
        with ScrollableContainer():
            for name in self.value:
                with Horizontal():
                    yield Label(name)
                    yield Input(id=name)
            yield Footer()

    def on_mount(self) -> None:
        self.set_focus(self.query('Input').first())

    def on_input_changed(self, message):
        self.value[message.input.id] = message.value

    def action_submit(self):
        self.exit(self.value)


if __name__ == "__main__":
    result = DictApp(*input("Comma separated fields: ").split(',')).run(inline=True)
    print(result)
