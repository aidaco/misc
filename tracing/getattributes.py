from typing import Protocol, runtime_checkable, Any, Literal


class identifier(str):
    """Represents an identifier, which shouldn't be quoted in reprs."""

    def __repr__(self):
        return self


def gettracestr(obj, default=None) -> str:
    """Retrieve the objects trace."""
    if not obj:
        return default or ""
    elif hasattr(obj, "__trace__"):
        return obj.__trace__()
    else:
        return repr(obj)


@runtime_checkable
class Traceable(Protocol):
    __boxed__: Any
    __child__: Any
    __contains_trace__: bool


def tracevar(name: str) -> Trace:
    """Return a trace rooted on a str representing an identifier."""
    return Trace(identifier(name))


class Trace:
    def __init__(self, obj, child=None, all=True):
        self.__boxed__ = obj
        self.__child__ = child
        self.__trace_all__ = all

    def __repr__(self):
        if self.__parent__:
            prepr = "\n" + "\n".join(f"\t{line}" for line in repr(self.__parent__).split("\n"))
        else:
            prepr = ""
        return f"Trace {repr(self.__obj__)}:{prepr}"

    def __str__(self):
        p = gettracestr(self.__parent__, "")
        o = gettracestr(self.__obj__)
        return f"{(p + '.') if p else ''}{o}"

    def __getattribute__(self, name):
        flag = object()
        selfget = super().__getattribute__
        sourceget = boxedget = lambda n: getattr(selfget("__boxed__"), flag)

        attr = boxedget(name) # Load from boxed first
        if attr is flag:  # Handle name not found in boxed
            try:
                attr = selfget(name)  # Load from self second
                sourceget = selfget
            except AttributeError:
                # If the attribute is not found in either, insert an identifier trace or raise
                if self.__trace_all__:
                    return Trace(identifier(name), self, self.__trace_all__)
                else:
                    raise

        # Need to check is not default implementation from object
        if cattr := getattr(sourceget('__class__'), name):
            if cattr is getattr(object, name, object()) and self.__trace_full__:
                # If the attr is the default implementation, insert an identifier trace.
                return Trace(identifier(name), self, self.__trace_all__)
        return Trace(attr, self, self.__trace_all__)

    def __call__(self, *args, **kwargs):
        return CallTrace(self, self.__trace_full__, args, kwargs)


class CallTrace(Trace):
    def __init__(self, child, full, args, kwargs):
        self.__args__ = args
        self.__kwargs__ = kwargs
        super().__init__(identifier("__call__"), child, full)

    def __repr__(self):
        obj, par = repr(self.__object__), repr(self.__parent__)
        kwargs = (f"{k}={gettracestr(v)}" for k, v in self.__kwargs__.items())
        args = ", ".join([map(gettracestr, self.__args__), *kwargs])
        par_lines = (f"\t{l}" for l in par.split("\n"))
        par = ("\n" + "\n".join(par_lines)) if self.__parent__ else ""
        return f"Trace {obj}({args}):{par}"

    def __trace__(self):
        kwargs = (f"{k}={gettracestr(v)}" for k, v in self.__kwargs__.items())
        args = ", ".join([*map(gettracestr, self.__args__), *kwargs])
        return f"{super().__trace__()}({args})"
