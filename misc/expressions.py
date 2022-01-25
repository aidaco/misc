import functools
import typing
import types


T = typing.TypeVar("T")


@typing.runtime_checkable
class Encode(typing.Generic[T], typing.Protocol):
    def __call__(enc: T, spec: str | None = None, **kwargs) -> typing.Any:
        ...


@typing.runtime_checkable
class Encodable(typing.Generic[T], typing.Protocol):
    __encode__: Encode[T]


def encode_str(s, spec: str, **kwargs):
    match spec:
        case 'pystr':
            return repr(s) if kwargs.get('repr',  True) else str(s)

__encoders__: dict[typing.Type, Encode] = {
        object: lambda obj, spec=None, **kwargs: repr(obj),
}


def set_encoder(t: typing.Type, enc: Encode[T]):
    global __encoders__
    __encoders__[t] = enc


def remove_encoder(t: typing.Type):
    global __encoders__
    del __encoders__[t]


def encode(obj: typing.Any, spec: str | None = None, /, **kwargs) -> typing.Any:
    global __encoders__
    if isinstance(obj, Encodable):
        enc = obj.__encode__
    elif fn := __encoders__.get(type(obj), None):
        enc = functools.partial(fn, obj)
    else:
        enc = functools.partial(__encoders__[object], obj)
    args = [spec] if spec else []
    return enc(*args, **kwargs)


class Arguments(typing.NamedTuple):
    args: list
    kwargs: dict

    def __encode__(self, spec: str, **kwargs):
        a = (encode(a, spec, repr=True,  **kwargs) for a in self.args)
        kw = ((k, encode(v, spec, repr=True, **kwargs)) for k, v in self.kwargs.items())
        match spec:
            case 'pystr':
                return f'{", ".join([*a, *(f"{k}={v}" for k, v in kw)])}'



class MethodCall(typing.NamedTuple):
    obj: typing.Any
    method: str
    args: Arguments

    def __encode__(self, spec: str, **kwargs):
        obj = encode(self.obj, spec, **kwargs)
        method = self.method
        args = encode(self.args, spec, **kwargs)
        match spec:
            case 'pystr':
                return f"{obj}.{method}({args})"

    def __repr__(self):
        return encode(self, 'pystr')


def Operator(symbol: str):
    class OperatorCall(MethodCall):
        def __encode__(self, spec: str, **kwargs):
            nonlocal symbol
            obj = encode(self.obj, spec, **kwargs)
            arg = encode(self.args, spec, **kwargs)
            match spec:
                case 'pystr':
                    return f"({obj} {symbol} {arg})"
    return OperatorCall

class GetAttributeCall(MethodCall):
    def __encode__(self, spec: str, **kwargs):
        obj = encode(self.obj, spec, **kwargs)
        args = encode(self.args, spec, **kwargs)
        match spec:
            case 'pystr':
                return f"{obj}.{self.args.args[0]}"


class CallCall(MethodCall):
    def __encode__(self, spec: str, **kwargs):
        obj = encode(self.obj, spec, **kwargs)
        arg = encode(self.args, spec, **kwargs)
        match spec:
            case 'pystr':
                return f"{obj}({arg})"

class MethodTracer:
    def __init__(self, trace: typing.Any):
        self.trace = trace

    @classmethod
    def tracemethod(cls, name: str, callcls: typing.Type = MethodCall):
        def traced(self, *args, **kwargs):
            self.trace = callcls(self.trace, name, Arguments(args, kwargs))
            return self

        setattr(cls, name, traced)

    def __repr__(self):
        return encode(self.trace)

    def __encode__(self, spec: str = 'pystr', **kwargs):
        return encode(self.trace, spec, **kwargs)


def trace(name: str):
    class Tracer(MethodTracer):
        ...

    for method, call in SPECIAL_METHOD.items():
        if isinstance(call, typing.Type) and issubclass(call, MethodCall):
            Tracer.tracemethod(method, call)
        else:
            Tracer.tracemethod(method)
    return Tracer(name)


SPECIAL_METHOD = {
    "__lt__": Operator('<'),
    "__le__": Operator("<="),
    "__eq__": Operator("=="),
    "__ne__": Operator("!="),
    "__ge__": Operator(">="),
    "__gt__": Operator(">"),
    "__not__": "NOT",
    "__add__": Operator("+"),
    "__and__": "AND",
    "__truediv__": Operator("/"),
    "__floordiv__": Operator("//"),
    "__invert__": "~",
    "__mod__": Operator("%"),
    "__mul__": Operator("*"),
    "__or__": Operator("|"),
    "__pow__": Operator("**"),
    "__sub__": Operator("-"),
    "__xor__": Operator("^"),
    "__contains__": "in",
    "__getattr__": GetAttributeCall,
    "__call__": CallCall,
}
