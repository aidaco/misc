from inspect import signature


class typedispatch:
    """Multiple dispatch for functions/methods using type annotations.

    - Function:

        >>>@typedispatch
        >>>def foo(a: int, b: int):
        >>>    return a + b
        >>>
        >>>@foo.overload
        >>>def foo(a: int, b: str):
        >>>    return str(a) + b
        >>>
        >>>class A:
        >>>    @typedispatch
        >>>    def foo(self, a: int, b: int):
        >>>        return a + b
        >>>
        >>>    @foo.overload
        >>>    def foo(self, a: int, b: str):
        >>>        return str(a) + b
        >>>
        >>>a = A()
        >>>assert foo(1, 2) == 3
        >>>assert foo(1, '2') == '12'
        >>>assert a.foo(1, 2) == 3
        >>>assert a.foo(1, '2') == '12'
    """

    def __init__(self, fn=None, table=None, instance=None):
        self.table = table or []
        self.instance = instance
        if fn:
            self.overload(fn)

    def __get__(self, instance, cls):
        """Capture & bind the instance for method dispatching, return self."""

        self.instance = instance
        return self

    def overload(self, fn):
        """Add the callable to the dispatch table and return self."""

        self.table.append((fn, signature(fn)))
        return self

    def resolve(self, args: list, kwargs: dict):
        for fn, sig in self.table:
            try:
                # If dispatching a method insert the bound instance
                if self.instance:
                    bound = sig.bind(self.instance, *args, **kwargs)
                else:
                    bound = sig.bind(*args, **kwargs)
                ap = bound.arguments, sig.parameters

                # Generate the set of non-defaulted arguments
                argp = ([m[k] for m in ap] for k in set.intersection(*map(set, ap)))

                # Verify type hints, where available
                for arg, par in argp:
                    if par.annotation is not par.empty:
                        assert isinstance(arg, par.annotation)
                return fn, args, kwargs
            except (TypeError, AssertionError) as e:
                # Exception means signature mismatch, continue resolution
                continue
        else:
            raise ValueError(
                f"No overload found for {(args, kwargs)}, available: {[t[1] for t in self.table]}"
            )

    def __call__(self, *args, **kwargs):
        """Resolve & dispatch the function call."""
        fn, args, kwargs = self.resolve(args, kwargs)
        return fn(*args, **kwargs)
