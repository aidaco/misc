from enum import StrEnum
from typing import Any



class Op(StrEnum):
    ATTR = 'attr'
    ITEM = 'item'


class Term(StrEnum):
    SET = 'set'
    CALL = 'call'


type Step = tuple[Op, Any]
type End = tuple[Term, Any]
type Steps = list[tuple[Op, Any]]
type Path = tuple[Steps, End]


class Trace:
    __target__: Any
    __subscriptions__: dict
    __steps__: Steps

    def __init__(self, target: Any, subscriptions: dict | None = None, steps: Steps | None = None):
        object.__setattr__(self, '__target__', target)
        object.__setattr__(self, '__steps__', [] if steps is None else steps)
        object.__setattr__(self, '__subscriptions__', {} if subscriptions is None else subscriptions)

    def get(self):
        return self.__target__

    def subscribe(self, fn):
        tree = self.__subscriptions__
        for step in self.__steps__:
            tree = tree.setdefault(step, {})
        tree.setdefault(..., []).append(fn)

    def unsubscribe(self, fn):
        tree = self.__subscriptions__
        for step in self.__steps__:
            tree = tree.setdefault(step, {})
        tree.setdefault(..., []).remove(fn)

    def notify(self, path: Path):
        subscriptions = []
        tree = self.__subscriptions__
        steps, term = path
        for step in steps:
            subscriptions.extend(tree.get(..., []))
            tree = tree.setdefault(step, {})
        subscriptions.extend(tree.get(..., []))
        for subscription in subscriptions:
            subscription(path)

    def __getattr__(self, name):
        return Trace(
            target=getattr(self.__target__, name),
            subscriptions=self.__subscriptions__,
            steps=[*self.__steps__, (Op.ATTR, name)]
        )

    def __getitem__(self, key):
        return Trace(
            target=self.__target__[key],
            subscriptions=self.__subscriptions__,
            steps=[*self.__steps__, (Op.ITEM, key)]
        )

    def __setattr__(self, name, value):
        setattr(self.__target__, name, value)
        self.notify(
            ([*self.__steps__, (Op.ATTR, name)], (Term.SET, value))
        )

    def __setitem__(self, key, value):
        self.__target__[key] = value
        self.notify(
            ([*self.__steps__, (Op.ITEM, key)], (Term.SET, value))
        )

    def __call__(self, *args):
        self.__target__(*args)
        self.notify(
            (self.__steps__, (Term.CALL, args))
        )

    def __repr__(self):
        cls = self.__class__
        return f'{cls}(steps={get_steps_str(self.__steps__)}, target={self.__target__!r})'


def get_steps_str(steps: Steps) -> str:
    out = '$'
    for step in steps:
        match step:
            case [Op.ATTR, name]:
                out = f'{out}.{name}'
            case [Op.ITEM, key]:
                out = f'{out}[{key}]'
    return out


def get_path_str(path: Path) -> str:
    steps, term = path
    out = get_steps_str(steps)
    match term:
        case [Term.SET, value]:
            out = f'{out} = {value}'
        case [Term.CALL, args]:
            out = f'{out}({', '.join(map(str, args))})'
    return out
