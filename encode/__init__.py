import typing


@typing.runtime_checkable
class Encode(typing.Generic[T], typing.Protocol):
    def __call__(enc: T, spec: str | None = None, **kwargs) -> typing.Any:
        ...


@typing.runtime_checkable
class Encodable(typing.Generic[T], typing.Protocol):
    __encode__: Encode[T]


def encode_str(s, spec: str, **kwargs):
    match spec:
        case "pystr":
            return repr(s) if kwargs.get("repr", True) else str(s)


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
