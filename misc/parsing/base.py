from dataclasses import dataclass
from contextlib import contextmanager
from typing import TypeAlias, Self, Any, Callable, Generic, TypeVar


class ParseError(Exception):
    pass


class Unexpected(ParseError):
    pass


class EOSType:
    pass


BOS = object()
EOS = object()


@dataclass
class State:
    source: str
    pos: int = -1

    @property
    def maxpos(self) -> int:
        return len(self.source) - 1

    @property
    def value(self) -> BOS | str | EOS:
        if self.pos < 0:
            return BOS
        elif self.pos > self.maxpos:
            return EOS
        return self.source[self.pos]

    def advance(self) -> Self:
        if self.value is EOS:
            return self
        self.pos += 1
        return self


def unexpected(state: State) -> None:
    raise ParseError(f"Unexpected value [{state.value}] at index [{state.pos}].")


class Parse:
    def char(state: State) -> tuple[str, State]:
        if state.value is EOS:
            unexpected(state)
        return state.value, state.next

    def literal(state: State, value) -> tuple[Any, State]:
        if state.value != value:
            state.unexpected()
        return state.value, state.next


class Parser:
    def __init__(self, parser):
        self.parser = parser

    def then(self, parser):
        def then(state: State):
            self.parser(state)
            parser(state)

        return ParserCombinator(then)

    def expect(self, value) -> Self:
        def parse(state: State):
            obj, next_state = self.parser(state)
            if obj != value:
                unexpected(state)
            return obj, next_state

        return ParserCombinator(parse)

    def parse(self, state: State):
        return self.parser(state)
