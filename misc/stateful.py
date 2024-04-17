from dataclasses import dataclass, field
import sys
from typing import (
    Any,
    Iterator,
    Iterable,
    Literal,
    Sequence,
    Callable,
    TypedDict,
    Type,
    Self,
)


Event = TypedDict
type HandlerType[E: Event] = Callable[[E], None]


@dataclass
class EventBus[E: Event]:
    listeners: set[HandlerType[E]] = field(default_factory=set)

    def listen(self, handler: HandlerType[E]) -> None:
        self.listeners.add(handler)

    def unlisten(self, handler: HandlerType[E]) -> None:
        self.listeners.remove(handler)

    def dispatch(self, event: E) -> None:
        for listener in self.listeners:
            listener(event)


class ValueEvent[V](Event):
    type: Literal["value"]
    value: V


class Value[V]:
    value: V
    events: EventBus[ValueEvent[V]]

    def __init__(self, value: V):
        self.value = value
        self.events = EventBus()

    def listen(self, handler: HandlerType[ValueEvent[V]]) -> None:
        handler({"type": "value", "value": self.value})
        self.events.listen(handler)

    def unlisten(self, handler: HandlerType[ValueEvent[V]]) -> None:
        self.events.unlisten(handler)

    def get(self):
        return self.value

    def set(self, value):
        if value != self.value:
            self.value = value
            self.events.dispatch({"type": "value", "value": value})


class ValueProperty[V]:
    name: str
    owner: Type
    initial: V

    def __init__(self, initial: V) -> None:
        self.initial = initial

    def __set_name__(self, owner: Type, name: str) -> None:
        self.owner = owner
        self.name = name

    def __get__(self, owner, cls=None) -> Value[V]:
        if owner is None:
            return self  # type: ignore
        return self.value(owner)

    def __set__(self, owner, value: V) -> None:
        self.value(owner).set(value)

    def value(self, owner) -> Value[V]:
        try:
            return getattr(owner, f"_{self.name}")
        except AttributeError:
            value = Value(self.initial)
            setattr(owner, f"_{self.name}", value)
            return value

    def listen(self, owner, handler: HandlerType[ValueEvent[V]]) -> None:
        self.value(owner).listen(handler)

    def unlisten(self, owner, handler: HandlerType[ValueEvent[V]]) -> None:
        self.value(owner).unlisten(handler)


class ClearEvent(Event):
    type: Literal["clear"]


class AppendEvent[V](Event):
    type: Literal["append"]
    value: V


class ExtendEvent[V](Event):
    type: Literal["extend"]
    values: Sequence[V]


class IndexEvent[V](Event):
    type: Literal["set", "insert", "delete"]
    index: int
    value: V


type ListEvents[V] = (
    ValueEvent[list[V]] | ClearEvent | AppendEvent[V] | IndexEvent[V] | ExtendEvent[V]
)


class List[V]:
    value: list[V]
    events: EventBus[ListEvents[V]]

    def __init__(self, *initial: V):
        self.value = list(initial)
        self.events = EventBus()

    def listen(self, handler: HandlerType[ListEvents[V]]) -> None:
        handler({"type": "value", "value": self.value})
        self.events.listen(handler)

    def unlisten(self, handler: HandlerType[ListEvents[V]]) -> None:
        self.events.unlisten(handler)

    def clear(self) -> None:
        self.value.clear()
        self.events.dispatch({"type": "clear"})

    def append(self, value: V) -> None:
        self.value.append(value)
        self.events.dispatch({"type": "append", "value": value})

    def extend(self, values: Sequence[V]) -> None:
        self.value.extend(values)
        self.events.dispatch({"type": "extend", "values": values})

    def insert(self, index: int, value: V) -> None:
        self.value.insert(index, value)
        self.events.dispatch({"type": "insert", "index": index, "value": value})

    def pop(self, index: int = -1) -> V:
        value = self.value.pop(index)
        self.events.dispatch({"type": "delete", "index": index, "value": value})
        return value

    def remove(self, value: V) -> None:
        ix = self.value.index(value)
        del self.value[ix]
        self.events.dispatch({"type": "delete", "index": ix, "value": value})

    def __setitem__(self, index: int, value: V) -> None:
        self.value[index] = value
        self.events.dispatch({"type": "set", "index": index, "value": value})

    def __delitem__(self, index: int) -> None:
        value = self.value.pop(index)
        self.events.dispatch({"type": "delete", "index": index, "value": value})

    def count(self, value: V) -> int:
        return self.value.count(value)

    def index(self, value: V, start: int = 0, stop: int = sys.maxsize) -> int:
        return self.value.index(value, start, stop)

    def __getitem__(self, index: int) -> V:
        return self.value[index]

    def __add__(self, other: list[V]) -> list[V]:
        return self.value + other

    def __contains__(self, value: V) -> bool:
        return value in self.value

    def __eq__(self, other: Self) -> bool:
        return self.value == other.value

    def __iter__(self) -> Iterator[V]:
        return iter(self.value)

    def __len__(self) -> int:
        return len(self.value)

    def __repr__(self) -> str:
        return repr(self.value)

    def __str__(self) -> str:
        return str(self.value)


class ListProperty[V]:
    name: str
    owner: Type
    initial: list[V]

    def __init__(self, *initial: V) -> None:
        self.initial = list(initial)

    def __set_name__(self, owner: Type, name: str) -> None:
        self.owner = owner
        self.name = name

    def __get__(self, owner, cls=None) -> List[V]:
        if owner is None:
            return self  # type: ignore
        return self.value(owner)

    def __set__(self, owner, value: list[V]) -> None:
        inst = self.value(owner)
        if value != inst.value:
            inst.value = value
            inst.events.dispatch({"type": "value", "value": value})

    def value(self, owner) -> List[V]:
        try:
            return getattr(owner, f"_{self.name}")
        except AttributeError:
            value = List(*self.initial)
            setattr(owner, f"_{self.name}", value)
            return value

    def listen(self, owner, handler: HandlerType[ListEvents[V]]) -> None:
        self.value(owner).listen(handler)

    def unlisten(self, owner, handler: HandlerType[ListEvents[V]]) -> None:
        self.value(owner).unlisten(handler)


class InsertEvent(Event):
    type: Literal["insert"]
    index: int
    value: str


class DeleteRangeEvent(Event):
    type: Literal["delete"]
    index: int
    length: int


type StringEvents = (
    AppendEvent[str] | InsertEvent | DeleteRangeEvent | ValueEvent[str] | ClearEvent
)


class String:
    value: str
    events: EventBus[StringEvents]

    def __init__(self, initial: str):
        self.value = initial
        self.events = EventBus()

    def listen(self, handler: HandlerType[StringEvents]) -> None:
        handler({"type": "value", "value": self.value})
        self.events.listen(handler)

    def unlisten(self, handler: HandlerType[StringEvents]) -> None:
        self.events.unlisten(handler)

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value
        self.events.dispatch({"type": "value", "value": value})

    def clear(self) -> None:
        self.value = ""
        self.events.dispatch({"type": "clear"})

    def append(self, value: str) -> None:
        self.value += value
        self.events.dispatch({"type": "append", "value": value})

    def insert(self, index: int, value: str) -> None:
        self.value = self.value[:index] + value + self.value[index:]
        self.events.dispatch({"type": "insert", "index": index, "value": value})

    def delete(self, index: int, length: int) -> None:
        self.value = self.value[:index] + self.value[index + length :]
        self.events.dispatch({"type": "delete", "index": index, "length": length})

    def count(self, value: str) -> int:
        return self.value.count(value)

    def index(self, value: str, start: int = 0, stop: int = sys.maxsize) -> int:
        return self.value.index(value, start, stop)

    def __getitem__(self, index: int) -> str:
        return self.value[index]

    def __add__(self, other: str) -> str:
        return self.value + other

    def __iadd__(self, other: str) -> str:
        self.value += other
        self.events.dispatch({"type": "append", "value": other})
        return self.value

    def __contains__(self, value: str) -> bool:
        return value in self.value

    def __eq__(self, other: Self) -> bool:
        return self.value == other.value

    def __iter__(self) -> Iterator[str]:
        return iter(self.value)

    def __len__(self) -> int:
        return len(self.value)

    def __repr__(self) -> str:
        return repr(self.value)

    def __str__(self) -> str:
        return self.value


class StringProperty:
    name: str
    owner: Type
    initial: str

    def __init__(self, initial: str) -> None:
        self.initial = initial

    def __set_name__(self, owner: Type, name: str) -> None:
        self.owner = owner
        self.name = name

    def __get__(self, owner, cls=None) -> String:
        if owner is None:
            return self  # type: ignore
        return self.value(owner)

    def __set__(self, owner, value: str) -> None:
        inst = self.value(owner)
        if value != inst.value:
            inst.value = value
            inst.events.dispatch({"type": "value", "value": value})

    def value(self, owner) -> String:
        try:
            return getattr(owner, f"_{self.name}")
        except AttributeError:
            value = String(self.initial)
            setattr(owner, f"_{self.name}", value)
            return value

    def listen(self, owner, handler: HandlerType[StringEvents]) -> None:
        self.value(owner).listen(handler)

    def unlisten(self, owner, handler: HandlerType[StringEvents]) -> None:
        self.value(owner).unlisten(handler)


class ItemEvent[K, V](Event):
    type: Literal["set", "delete"]
    key: K
    value: V


class UpdateEvent[K, V](Event):
    type: Literal["update"]
    values: dict[K, V]


type DictEvents[K, V] = (
    ItemEvent[K, V] | ClearEvent | UpdateEvent[K, V] | ValueEvent[dict[K, V]]
)


class DEFAULT:
    pass


class Dict[K, V]:
    value: dict[K, V]
    events: EventBus[DictEvents[K, V]]

    def __init__(self, *args, **kwargs):
        self.value = dict(*args, **kwargs)
        self.events = EventBus()

    def listen(self, handler: HandlerType[DictEvents[K, V]]) -> None:
        handler({"type": "value", "value": self.value})
        self.events.listen(handler)

    def unlisten(self, handler: HandlerType[DictEvents[K, V]]) -> None:
        self.events.unlisten(handler)

    def __contains__(self, key: K) -> bool:
        return key in self.value

    def __getitem__(self, key: K) -> V:
        return self.value[key]

    def __setitem__(self, key: K, value: V) -> None:
        self.value[key] = value
        self.events.dispatch({"type": "set", "key": key, "value": value})

    def __delitem__(self, key: K) -> None:
        value = self.value.pop(key)
        self.events.dispatch({"type": "delete", "key": key, "value": value})

    def __eq__(self, other: Self) -> bool:
        return self.value == other.value

    def __ior__(self, other: dict[K, V]) -> dict[K, V]:
        self.value |= other
        self.events.dispatch({"type": "update", "values": other})
        return self.value

    def __or__(self, other: dict[K, V]) -> dict[K, V]:
        return self.value | other

    def __ror__(self, other: dict[K, V]) -> dict[K, V]:
        return other | self.value

    def __iter__(self) -> Iterator[K]:
        return iter(self.value)

    def __len__(self) -> int:
        return len(self.value)

    def __repr__(self) -> str:
        return repr(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def clear(self) -> None:
        self.value.clear()
        self.events.dispatch({"type": "clear"})

    def get(self, key: K, default: V | None = None) -> V | None:
        return self.value.get(key, default)

    def pop(self, key: K, default: V | DEFAULT = DEFAULT()) -> V:
        try:
            value = self.value.pop(key)
            self.events.dispatch({"type": "delete", "key": key, "value": value})
            return value
        except KeyError as exc:
            if isinstance(default, DEFAULT):
                raise exc
            return default

    def popitem(self) -> tuple[K, V]:
        item = key, value = self.value.popitem()
        self.events.dispatch({"type": "delete", "key": key, "value": value})
        return item

    def setdefault(self, key: K, default: V) -> V:
        try:
            return self.value[key]
        except KeyError:
            self.value[key] = default
            self.events.dispatch({"type": "set", "key": key, "value": default})
            return default

    def update(self, other: dict[K, V] | None = None, **kwargs: V):
        values: dict[K, V]
        if other is not None:
            values = other | kwargs  # type: ignore
        else:
            values = kwargs  # type: ignore
        self.values.update(values)
        self.events.dispatch({"type": "update", "values": values})

    def keys(self) -> Iterable[K]:
        return self.value.keys()

    def values(self) -> Iterable[V]:
        return self.value.values()

    def items(self) -> Iterable[tuple[K, V]]:
        return self.value.items()


class DictProperty[K, V]:
    name: str
    owner: Type
    initial: Any

    def __init__(self, *args, **kwargs) -> None:
        self.initial = (args, kwargs)

    def __set_name__(self, owner: Type, name: str) -> None:
        self.owner = owner
        self.name = name

    def __get__(self, owner, cls=None) -> Dict[K, V]:
        if owner is None:
            return self  # type: ignore
        return self.value(owner)

    def __set__(self, owner, value: dict[K, V]) -> None:
        inst = self.value(owner)
        if value != inst.value:
            inst.value = value
            inst.events.dispatch({"type": "value", "value": value})

    def value(self, owner) -> Dict[K, V]:
        try:
            return getattr(owner, f"_{self.name}")
        except AttributeError:
            value = Dict(*self.initial[0], **self.initial[1])
            setattr(owner, f"_{self.name}", value)
            return value

    def listen(self, owner, handler: HandlerType[DictEvents[K, V]]) -> None:
        self.value(owner).listen(handler)

    def unlisten(self, owner, handler: HandlerType[DictEvents[K, V]]) -> None:
        self.value(owner).unlisten(handler)
