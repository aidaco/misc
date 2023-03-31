"""Screen filling animations in the terminal."""

import math
import random
import time
from itertools import chain, combinations
from typing import Callable

from blessed import Terminal


def itersleep(duration: float, steps: int):
    """Sleep for step seconds between iterations up to total seconds.

    Yields total elapsed time. Does not account for user execution time."""

    total_elapsed = 0
    step_time = duration / steps
    while total_elapsed < duration:
        yield total_elapsed
        time.sleep(step_time)
        total_elapsed += step_time
    yield duration


def splashscreen(terminal: Terminal, text: str, duration: float):
    """Display the text in the center of the screen for a specified time."""

    bg = "\n".join(
        "".join(" " for x in range(terminal.width)) for y in range(terminal.height)
    )
    print(
        terminal.clear
        + terminal.home
        + bg
        + terminal.move_y(terminal.height // 2)
        + terminal.center(text)
    )
    time.sleep(duration)


def screenfill(
    terminal: Terminal,
    *,
    char: str = "*",
    steps: int = 60,
    duration: float = 1.0,
    func: Callable[[int, int, float], list[list[bool]]],
):
    """Animate filling the screen with the given character."""

    w, h = terminal.width, terminal.height
    for etime in itersleep(duration, steps):
        should_fill = func(w, h, etime / duration)
        output = "\n".join(
            "".join(char if flag else " " for flag in row) for row in should_fill
        )
        print(terminal.home + output)


def circle(width: int, height: int, percent: float) -> list[list[bool]]:
    radius = math.sqrt(width**2 + height**2) * percent
    return [
        [math.sqrt(x**2 + y**2) <= radius for x in range(width)]
        for y in range(height)
    ]


def static(width: int, height: int, percent: float) -> list[list[bool]]:
    return [[random.random() < percent for x in range(width)] for y in range(height)]


def left_to_right(width: int, height: int, percent: float) -> list[list[bool]]:
    return [[x / width <= percent for x in range(width)] for y in range(height)]


def top_to_bottom(width: int, height: int, percent: float) -> list[list[bool]]:
    return [[y / height <= percent for x in range(width)] for y in range(height)]


def topleft_to_bottomright(width: int, height: int, percent: float) -> list[list[bool]]:
    return [
        [((y / height) + (x / width)) / 2 < percent for x in range(width)]
        for y in range(height)
    ]


def inverted(
    func: Callable[[...], list[list[bool]]]
) -> Callable[[...], list[list[bool]]]:
    def invert(*args, **kwargs):
        res = func(*args, **kwargs)
        return [[not val for val in row] for row in res]

    return invert


def reversed(
    func: Callable[[...], list[list[bool]]]
) -> Callable[[...], list[list[bool]]]:
    def reverse(width: int, height: int, percent: float, *args, **kwargs):
        return func(width, height, 1 - percent, *args, **kwargs)

    return reverse


def flippedx(
    func: Callable[[...], list[list[bool]]]
) -> Callable[[...], list[list[bool]]]:
    def flipx(*args, **kwargs):
        res = func(*args, **kwargs)
        return [row[::-1] for row in res]

    return flipx


def flippedy(
    func: Callable[[...], list[list[bool]]]
) -> Callable[[...], list[list[bool]]]:
    def flipy(*args, **kwargs):
        res = func(*args, **kwargs)
        return res[::-1]

    return flipy


if __name__ == "__main__":
    t = Terminal()
    funcs = [
        circle,
        static,
        left_to_right,
        top_to_bottom,
        topleft_to_bottomright,
    ]
    modifiers = [
        flippedx,
        flippedy,
        inverted,
        reversed,
    ]
    mod_combos = list(
        chain(*(combinations(modifiers, n) for n in range(1, len(modifiers) + 1)))
    )
    with t.hidden_cursor(), t.fullscreen():
        for base in funcs:
            splashscreen(t, f"{base.__name__}", 1)
            screenfill(t, func=base)
            for mods in mod_combos:
                splashscreen(
                    t, f"{base.__name__} {' -> '.join(f.__name__ for f in mods)}", 1
                )
                func = base
                for mod in mods:
                    func = mod(func)
                screenfill(t, func=func)
