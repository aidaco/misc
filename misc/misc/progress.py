import time
from dataclasses import dataclass
from math import floor
from threading import Thread

from rich.columns import Columns
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.segment import Segment
from rich.table import Table


@dataclass
class Progress:
    status: int
    total: int
    width: int = 25

    @property
    def ratio(self):
        return self.status / self.total

    @property
    def done(self):
        return self.status == self.total

    def tick(self):
        self.status += 1

    def __rich__(self):
        wleft = round(self.width * self.ratio)
        wright = self.width - wleft
        stars = "█" * wleft
        spaces = " " * wright
        return f"[bold yellow]|[/][bold cyan]{stars}{spaces}[/][bold yellow]|[/]"


class PThread(Thread):
    def __init__(self, progress, dur):
        self.progress = progress
        self.inter = dur / progress.total
        super().__init__()

    def __rich__(self):
        return f"[{self.progress.ratio * 100:.1f}]"

    def run(self):
        while not self.progress.done:
            self.progress.tick()
            time.sleep(self.inter)


def run(dur, total):
    p = Progress(0, total)
    pt = PThread(p, dur)
    t = Table("Progress", "Value")
    t.add_row(p, pt)
    with Live(t, refresh_per_second=30, transient=True):
        pt.start()
        pt.join()
    print(f"Finished {p.total}")


run(1, 1000)
