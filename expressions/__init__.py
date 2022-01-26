import functools
import typing

import encode


class Arguments(typing.NamedTuple):
    args: list
    kwargs: dict

    def __encode__(self, spec: str, **kwargs):
        a = (encode.encode(a, spec, repr=True, **kwargs) for a in self.args)
        kw = ((k, encode.encode(v, spec, repr=True, **kwargs)) for k, v in self.kwargs.items())
        match spec:
            case "pystr" | "python.expression":
                return f'{", ".join([*a, *(f"{k}={v}" for k, v in kw)])}'


class MethodCall(typing.NamedTuple):
    obj: typing.Any
    method: str
    args: Arguments

    def __encode__(self, spec: str, **kwargs):
        obj = encode.encode(self.obj, spec, **kwargs)
        method = self.method
        args = encode.encode(self.args, spec, **kwargs)
        match spec:
            case "pystr":
                return f"{obj}.{method}({args})"

    def __repr__(self):
        return encode.encode(self, "pystr")


def Operator(symbol: str):
    class OperatorCall(MethodCall):
        def __encode__(self, spec: str, **kwargs):
            nonlocal symbol
            obj = encode.encode(self.obj, spec, **kwargs)
            arg = encode.encode(self.args, spec, **kwargs)
            match spec:
                case "pystr":
                    return f"({obj} {symbol} {arg})"

    return OperatorCall


class GetAttributeCall(MethodCall):
    def __encode__(self, spec: str, **kwargs):
        obj = encode.encode(self.obj, spec, **kwargs)
        args = encode.encode(self.args, spec, **kwargs)
        match spec:
            case "pystr":
                return f"{obj}.{self.args.args[0]}"


class CallCall(MethodCall):
    def __encode__(self, spec: str, **kwargs):
        obj = encode.encode(self.obj, spec, **kwargs)
        arg = encode.encode(self.args, spec, **kwargs)
        match spec:
            case "pystr":
                return f"{obj}({arg})"


class MethodTrace:
    def __init__(trace, obj: typing.Any, method: str, args: Arguments):
        trace.obj = obj
        trace.method = method
        trace.args = args
        # print(f"{trace.__class__.__name__} :: {encode.encode(trace, 'python.expression')}")

    def __encode__(trace, spec: str, **kwargs):
        obj = encode.encode(trace.obj, spec, **kwargs)
        method = trace.method
        args = encode.encode(trace.args, spec, **kwargs)
        match spec:
            case "python.expression" | "pystr":
                return f"{obj}.{method}({args})"

    def __repr__(self):
        return encode.encode(self, "python.expression")


class VariableTrace(MethodTrace):
    def __init__(self, name: str):
        super().__init__(name, "", Arguments([], {}))

    def __encode__(self, spec: str, **kwargs):
        match spec:
            case "python.expression":
                return f"{encode.encode(self.obj, spec, **kwargs)}"


class AttributeTrace(MethodTrace):
    def __encode__(self, spec: str, **kwargs):
        obj = encode.encode(self.obj, spec, **kwargs)
        arg = encode.encode(self.args, spec, **kwargs)
        match spec:
            case "python.expression" | "pystr":
                return f"{obj}.{arg})"


def OperatorTrace(symbol: str):
    class trace(MethodTrace):
        def __encode__(self, spec: str, **kwargs):
            nonlocal symbol
            obj = encode.encode(self.obj, spec, **kwargs)
            arg = encode.encode(self.args, spec, **kwargs)
            match spec:
                case "python.expression" | "pystr":
                    return f"({obj} {symbol} {arg})"

    return trace


class SubscriptTrace(MethodTrace):
    def __encode__(self, spec: str, **kwargs):
        obj = encode.encode(self.obj, spec, **kwargs)
        args = encode.encode(self.args, spec, **kwargs)
        match spec:
            case "python.expression" | "pystr":
                return f"{obj}[{args}]"


class ContainsTrace(MethodTrace):
    def __encode__(trace, spec: str, **kwargs):
        obj = encode.encode(trace.obj, spec, **kwargs)
        args = encode.encode(trace.args, spec, **kwargs)
        match spec:
            case "python.expression" | "pystr":
                return f"{args} in {obj}"


class Traces:
    def __init__(self, **traces: typing.Type):
        self.traces = traces
        self._classmap = None

    @property
    def classmap(self):
        if self._classmap:
            return self._classmap
        clscopies = {t: self.copy_trace(t) for t in set(self.traces.values())}
        self._classmap = {name: clscopies[tracecls] for name, tracecls in self.traces.items()}
        for cls in self._classmap.values():
            for name, other in self._classmap.items():
                addtrace(cls, name, other)
        return self.classmap

    def copy_trace(self, trace):
        return type(f"Trace[{trace.__name__}]", (trace,), {})


def addtrace(cls, name: str, tracecls: typing.Type):
    def traced(obj, *args, **kwargs):
        _ = tracecls(obj, name, Arguments(args, kwargs))
        # print(f"TRACED :: {type(_)} {_}")
        return _

    setattr(cls, name, traced)


def withtraces(cls, **kwargs: typing.Type) -> typing.Type:
    for n, t in Traces(**kwargs).classmap.items():
        addtrace(cls, n, t)
    return cls


MINIMAL_TRACES = {
    "__getattr__": AttributeTrace,
    "__call__": MethodTrace,
    "__contains__": ContainsTrace,
}


def minimaltrace(name: str, tracecls: typing.Type = VariableTrace):
    cls = withtraces(type(f"trace<{name}>", (tracecls,), {}), **MINIMAL_TRACES)
    return cls(name)


SYNTAX_TRACES = {
    "__call__": MethodTrace,
    "__getitem__": SubscriptTrace,
    "__contains__": "in",
}

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
    "__not__": "not",
    "__invert__": "~",
    "__contains__": "in",
}


class MethodCallTracer:
    def __init__(self, trace: typing.Any):
        self.trace = trace

    @classmethod
    def tracemethod(cls, name: str, callcls: typing.Type = MethodCall):
        def traced(self, *args, **kwargs):
            self.trace = callcls(self.trace, name, Arguments(args, kwargs))
            return self

        setattr(cls, name, traced)

    def __repr__(self):
        return encode.encode(self.trace)

    def __encode__(self, spec: str = "pystr", **kwargs):
        return encode.encode(self.trace, spec, **kwargs)


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
    "__lt__": Operator("<"),
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
