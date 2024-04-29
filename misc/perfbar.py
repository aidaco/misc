from typing import Callable, Literal
import datetime
from math import floor
from pathlib import Path
from itertools import islice

import cyclopts
import psutil
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult, Group
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.measure import Measurement, measure_renderables
from rich.style import StyleType


class StatDisplay:
    def __init__(
        self,
        render_fn: Callable[[int, int], RenderableType] | None = None,
        style: StyleType = "black on white",
    ):
        self.style = style
        self.render_fn: Callable[[int, int], RenderableType] | None = render_fn

    def __call__(
        self, render_fn: Callable[[int, int], RenderableType]
    ) -> Callable[[int, int], RenderableType]:
        self.render_fn = render_fn
        return render_fn

    def _render(self, width: int, height: int) -> RenderableType:
        render: Callable[[int, int], RenderableType] = self.render_fn or getattr(
            self, "render"
        )
        assert render is not None
        return render(width, height)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        yield self._render(options.min_width, options.min_width)

    def __rich__(self) -> RenderableType:
        return self

    def __rich_measure__(self, console: Console, options: ConsoleOptions):
        return measure_renderables(
            console, options, [self._render(options.min_width, options.min_width)]
        )


class CurrentTimeDisplay(StatDisplay):
    def render(self, width: int, height: int) -> RenderableType:
        dt = f"{datetime.datetime.now(tz=datetime.timezone.utc).astimezone():%c %Z}"
        # spaces = " " * (width - len(dt))
        return Text(f"{dt}", style=self.style)


class CurrentWorkingDirectoryDisplay(StatDisplay):
    def render(self, width: int, height: int) -> RenderableType:
        return Group(
            *islice(
                (
                    Text(
                        path.name + (" " * (width - len(path.name))),
                        style=self.style,
                    )
                    for path in Path.cwd().iterdir()
                ),
                height - 1,
            )
        )


class PercentDisplay(StatDisplay):
    def __init__(
        self, name: str, get_percent: Callable[[], float], *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.name = name
        self.get_percent = get_percent

    def render(self, width: int, height: int) -> RenderableType:
        return Text(f"[{self.name} : {self.get_percent(): >4.1%}]", style=self.style)


class PercentBarDisplay(PercentDisplay):
    def render(self, width: int, height: int) -> RenderableType:
        stat_pct = self.get_percent()
        width = width - (len(self.name) + 2)
        bar_size = floor(stat_pct * width)
        empty_size = width - bar_size
        return Text(
            f'{self.name}[{"▦" * bar_size}{" " * empty_size}]', style=self.style
        )


class HGroup:
    def __init__(self, *widgets: RenderableType, style: StyleType = "black on white"):
        self.widgets = widgets
        self.style = style

    def __rich__(self) -> RenderableType:
        t = Table(
            *(" " for _ in range(len(self.widgets))),
            show_header=False,
            show_edge=True,
            show_footer=False,
            show_lines=False,
            pad_edge=False,
            collapse_padding=True,
            expand=True,
            padding=0,
            border_style=self.style,
        )
        t.add_row(*self.widgets)
        return t


class VGroup:
    def __init__(self, *widgets: RenderableType):
        self.widgets = widgets

    def __rich__(self) -> RenderableType:
        return Group(*self.widgets)


cli = cyclopts.App()


@cli.default
def main(orientation: Literal["vertical", "horizontal"] = "vertical", bar: bool = True):
    style = "bright_green"
    pct_cls = PercentDisplay if not bar else PercentBarDisplay
    match orientation:
        case "horizontal":
            widget = HGroup(
                VGroup(
                    CurrentTimeDisplay(style=style),
                    pct_cls(
                        "MEM",
                        lambda: psutil.virtual_memory().percent / 100,
                        style=style,
                    ),
                    pct_cls("CPU", lambda: psutil.cpu_percent() / 100, style=style),
                ),
                CurrentWorkingDirectoryDisplay(style=style),
                style=style,
            )
        case "vertical":
            widget = VGroup(
                HGroup(
                    CurrentTimeDisplay(style=style),
                    pct_cls(
                        "MEM",
                        lambda: psutil.virtual_memory().percent / 100,
                        style=style,
                    ),
                    pct_cls("CPU", lambda: psutil.cpu_percent() / 100, style=style),
                    style=style,
                ),
                # Panel(CurrentWorkingDirectoryDisplay(style=style), border_style=style),
                CurrentWorkingDirectoryDisplay(style=style),
            )
    try:
        with Live(widget, screen=True, refresh_per_second=1):
            while True:
                pass
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
