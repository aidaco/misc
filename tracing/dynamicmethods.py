import typing


class Arguments(typing.NamedTuple):
    args: list
    kwargs: dict

    def __repr__(self):
        a = (repr(a) for a in self.args)
        kw = ((k, repr(v)) for k, v in self.kwargs.items())
        return f'{", ".join([*a, *(f"{k}={v}" for k, v in kw)])}'


class MethodTrace:
    def __init__(trace, obj: typing.Any, method: str, args: Arguments):
        trace.obj = obj
        trace.method = method
        trace.args = args

    def __repr__(self):
        return f"{repr(self.obj)}.{repr(self.method)}({repr(self.args)})"


class CallTrace(MethodTrace):
    def __repr__(self) -> str:
        return f"{repr(self.obj)}({repr(self.args)})"


class VariableTrace(MethodTrace):
    def __init__(self, name: str):
        super().__init__(name, "", Arguments([], {}))

    def __repr__(self):
        return f"{repr(self.obj)}"


class AttributeTrace(MethodTrace):
    def __repr__(self):
        return f"{repr(self.obj)}.{repr(self.args)})"


def OperatorTrace(symbol: str):
    class _Trace(MethodTrace):
        def __repr__(self):
            return f"({repr(self.obj)} {repr(symbol)} {repr(self.args)})"

    return trace


def UnaryOperatorTrace(symbol: str):
    class _Trace(MethodTrace):
        def __repr__(self):
            return f"({symbol}{repr(self.obj)})"

    return trace


class SubscriptTrace(MethodTrace):
    def __repr__(self):
        return f"{self.obj}[{self.args}]"


class Traces:
    def __init__(self, **traces: typing.Type):
        self.traces = traces
        self._classmap = None

    @property
    def classmap(self):
        if self._classmap:
            return self._classmap
        clscopies = {t: self.copy_trace(t) for t in set(self.traces.values())}
        self._classmap = {
            name: clscopies[tracecls] for name, tracecls in self.traces.items()
        }
        for cls in self._classmap.values():
            for name, other in self._classmap.items():
                addtrace(cls, name, other)
        return self.classmap

    def copy_trace(self, trace):
        return type(f"Trace[{trace.__name__}]", (trace,), {})


def addtrace(cls, name: str, tracecls: typing.Type):
    def traced(obj, *args, **kwargs):
        return tracecls(obj, name, Arguments(args, kwargs))

    setattr(cls, name, traced)


def withtraces(cls, **kwargs: typing.Type) -> typing.Type:
    for n, t in Traces(**kwargs).classmap.items():
        addtrace(cls, n, t)
    return cls


def trace(name: str):
    class Tracer(VariableTrace):
        ...

    return withtraces(Tracer, **BUILTIN_TRACES)(name)


COMPARE_TRACES = {
    "__lt__": OperatorTrace("<"),
    "__le__": OperatorTrace("<="),
    "__eq__": OperatorTrace("=="),
    "__ne__": OperatorTrace("!="),
    "__ge__": OperatorTrace(">="),
    "__gt__": OperatorTrace(">"),
}

MATH_TRACES = {
    "__add__": OperatorTrace("+"),
    "__sub__": OperatorTrace("-"),
    "__mul__": OperatorTrace("*"),
    "__truediv__": OperatorTrace("/"),
    "__floordiv__": OperatorTrace("//"),
    "__mod__": OperatorTrace("%"),
    "__pow__": OperatorTrace("**"),
    "__matmul__": OperatorTrace("@"),
}

BINARY_TRACES = {
    "__and__": OperatorTrace("&"),
    "__or__": OperatorTrace("|"),
    "__xor__": OperatorTrace("^"),
    "__not__": UnaryOperatorTrace("not"),
    "__invert__": UnaryOperatorTrace("~"),
    "__contains__": OperatorTrace("in"),
}


BUILTIN_TRACES = {
    "__lt__": OperatorTrace("<"),
    "__le__": OperatorTrace("<="),
    "__eq__": OperatorTrace("=="),
    "__ne__": OperatorTrace("!="),
    "__ge__": OperatorTrace(">="),
    "__gt__": OperatorTrace(">"),
    "__not__": UnaryOperatorTrace("not"),
    "__add__": OperatorTrace("+"),
    "__and__": OperatorTrace("and"),
    "__truediv__": OperatorTrace("/"),
    "__floordiv__": OperatorTrace("//"),
    "__invert__": UnaryOperatorTrace("~"),
    "__mod__": OperatorTrace("%"),
    "__mul__": OperatorTrace("*"),
    "__or__": OperatorTrace("|"),
    "__pow__": OperatorTrace("**"),
    "__sub__": OperatorTrace("-"),
    "__xor__": OperatorTrace("^"),
    "__contains__": OperatorTrace("in"),
    "__getattr__": AttributeTrace,
    "__call__": CallTrace,
}
