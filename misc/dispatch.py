"""Multiple dispatch for functions & methods using type annotations by default.

Usage:

- Decorator
    ```python
    @dispatch
    def foo(a: int, b: int):
        return a + b

    @foo.overload
    def foo(a: int, b: str):
        return str(a) + b

    assert foo(1, 2) == 3
    assert foo(1, '2') == '12'
    ```

- Custom Lookup
    ```python
    from functools import cache
    class MyLookup(FullTypeLookup):
        @cache
        def resolve(self, *args, **kwargs):
            return super().resolve(*args, **kwargs)

    @dispatch(MyLookup)
    def foo(a: int, b: int):
        return a + b

    @foo.overload
    def foo(a: int, b: str):
        return str(a) + b

    foo(1)
    foo(2)
    foo(3)
    foo(1)
    cache_info = foo.cache_info()
    assert cache_info.misses == 3
    assert cache_info.hits == 1
    ```
"""

from inspect import signature
from typing import Type, Callable, Any, TypeVar, Generic, Protocol, runtime_checkable


def dispatch(lookupcls_or_fn: Lookup | Callable) -> Callable[..., Dispatch] | Dispatch:
    """Multiple dispatch for functions & methods, checks annotations by default."""
    global default_lookup

    def make_dispatch(fn, lookup):
        d = Dispatch(lookup)
        d.add(fn)
        return d

    # If lookupcls_or_fn is Lookup, return a decorator that passes it to make_dispatch
    # Otherwise return Dispatch with default lookup
    if isinstance(lookupcls_or_fn, Lookup):

        def decorate(fn: Callable) -> Dispatch:
            return make_dispatch(fn, lookupcls_or_fn)

        return decorate
    else:
        return make_dispatch(lookupcls_or_fn, default_lookup)


@runtime_checkable
class Lookup(Protocol):
    def add(self, fn: Callable) -> None:
        """Add callable to the lookup table."""

    def resolve(self, *args, **kwargs) -> Callable:
        """Resolve the arguments to a callable from the table."""


class Dispatch:
    """Multiple dispatch for functions & methods."""

    def __init__(self, lookup: Lookup, instance=None):
        self.lookup = lookup
        self.instance = instance

    def __get__(self, instance, cls):
        """If the dispatch is accessed from an instance, bind the instance."""

        return cls(instance=instance, lookup=self.lookup)

    def overload(self, fn: Callable):
        """Register callable with the lookup & return self."""

        self.lookup[fn] = fn
        return self

    def __call__(self, *args, **kwargs):
        """Resolve & dispatch the function call."""

        if self.instance:  # If dispatching a method insert the bound instance
            args = (self.instance, *args)
        return self.lookup.resolve(*args, **kwargs)(*args, **kwargs)


class SignatureLookup:
    def __init__(self):
        self.fns = []

    def __getitem__(self, fn: Callable):
        """Add callable to the lookup table."""
        self.fns.append(fn)

    def resolve(self, *args, **kwargs) -> Callable:
        """Return the most recently added callable that successfully binds to the unpacked varargs.

        Has the potential to perform many isinstance checks."""

        for fn in self.fns:
            try:
                signature(fn).bind(*args, **kwargs)
            except TypeError:
                continue
            else:
                return fn
        else:
            raise TypeError(f"No matches found for {[*args]}, {**kwargs}")


class FullTypeLookup(SignatureLookup):
    def resolve(self, *args, **kwargs) -> T:
        """Adds isinstance checks for annotations to SignatureLookup."""

        for fn in self.fns:
            # Attempt to bind the signature
            try:
                bound = signature(fn).bind(*args, **kwargs)
                ap = bound.arguments, sig.parameters

                # Generate the set of non-defaulted arguments
                argp = ([m[k] for m in ap] for k in set.intersection(*map(set, ap)))

                # Verify type hints, where available
                if all(
                    isinstance(arg, par.annotation)
                    for arg, par in argp
                    if par.annotation is not par.empty
                ):
                    return fn
            except TypeError:
                continue
        else:
            raise TypeError(f"No matches found for {[*args]}, {**kwargs}")


default_lookup = FullTypeLookup
