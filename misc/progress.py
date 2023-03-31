"""Simple progress bar."""

import time
from dataclasses import dataclass

from rich.live import Live


@dataclass
class Progress:
    total: int
    status: int = 0
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
        return f"[bold yellow]|[/][bold cyan]{stars}{spaces}[/][bold yellow]|[/][{self.ratio * 100: >5.1f}%]"

    def iter(self, it):
        with Live(self, refresh_per_second=30, transient=True):
            for i in it:
                yield i
                self.tick()


def spin(dur, n=1000):
    inter = dur / n

    def _count_timer():
        for i in range(n):
            time.sleep(inter)
            yield i

    p = Progress(n)
    for _ in p.iter(_count_timer()):
        ...


if __name__ == "__main__":
    spin(5)
