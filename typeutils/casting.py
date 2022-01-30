from inspect import signature
from typing import (
    Callable,
    Type,
    TypeVar,
    runtime_checkable,
    Generic,
    Protocol,
    Any,
)


From = TypeVar("From", contravariant=True)
To = TypeVar("To", covariant=True)


@runtime_checkable
class Cast(Generic[From, To], Protocol):
    """A Cast is any callable which provides a conversion from instances of one type to another."""

    def __call__(self, obj: From) -> To:
        ...


@runtime_checkable
class Caster(Protocol):
    """A Caster provides a mapping from a sequence of types to a Cast."""

    def __getitem__(self, casts: tuple[Type, Type]) -> Cast:
        ...

    def __setitem__(self, casts: tuple[Type, Type], fn: Callable) -> None:
        ...

    def __delitem__(self, casts: tuple[Type, Type]) -> None:
        ...


@runtime_checkable
class Castable(Protocol):
    __caster__: Caster


__caster__: Caster | None = None


def cast(obj: Any, target: Type):
    """Atempt to create an instance of type 't' from object 'o'.

    Looks for a Caster object in:
        - obj.__caster__
        - casting.__casters__
    """

    global __caster__
    if not __caster__:
        raise RuntimeError("No caster found")
    caster = getattr(obj, "__caster__", __caster__[type(obj), target])
    return caster(obj)


def caster(fn: Callable):
    global __caster__
    sig = signature(fn)
    o, d = sig.parameters[list(sig.parameters)[0]].annotation, sig.return_annotation
    if not __caster__:
        raise RuntimeError("No caster found")
    __caster__[o, d] = fn
    return fn
