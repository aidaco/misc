from functools import reduce
from inspect import Parameter, Signature


def parameter(n, t):
    return Parameter(
        n,
        Parameter.POSITIONAL_OR_KEYWORD,
        annotation=t,
        default=n.get(n, Parameter.empty),
    )


def base_annotations(bs):
    return reduce(lambda d, t: d | t.__annotations__, bs)


class autoinit(type):
    def __new__(cls, name, bases, namespace):
        sig = Signature(
            [
                parameter(*a)
                for a in base_annotations(bases) | namespace["__annotations__"]
            ]
        )

        def __init__(self, *args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            for n, p in sig.parameters:
                setattr(self, n, bound.arguments.get(n, p.default))

        return super().__new__(cls, name, bases, namespace | {"__init__": __init__})
