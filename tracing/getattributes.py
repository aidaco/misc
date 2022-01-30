class identifier(str):
    def __repr__(self):
        return self


def gettracestr(obj, default=None) -> str:
    if not obj:
        return default or ""
    elif isinstance(obj, Trace):
        return obj.__trace__()
    else:
        return repr(obj)


def tracevar(name):
    return Trace(identifier(name))


class Trace:
    def __init__(self, obj, parent=None, full=True):
        self.__full__ = full
        self.__obj__ = obj
        self.__parent__ = parent

    def __repr__(self):
        if self.__parent__:
            prepr = "\n" + "\n".join(
                f"\t{line}" for line in repr(self.__parent__).split("\n")
            )
        else:
            prepr = ""
        return f"Trace {repr(self.__obj__)}:{prepr}"

    def __trace__(self):
        p = gettracestr(self.__parent__, "")
        o = gettracestr(self.__obj__)
        return f"{(p + '.') if p else ''}{o}"

    def __getattribute__(self, name):
        name = identifier(name)
        print(f"GET {name}")
        try:
            t = super().__getattribute__(name)
            return t
        except AttributeError:
            try:
                t = Trace(getattr(self.__obj__, name), self)
                return t
            except AttributeError:
                if self.__full__:
                    return Trace(name, self)
                else:
                    raise

    def __call__(self, *args, **kwargs):
        return CallTrace(self, self.__full__, args, kwargs)


class CallTrace(Trace):
    def __init__(self, parent, full, args, kwargs):
        self.__args__ = args
        self.__kwargs__ = kwargs
        super().__init__(identifier("__call__"), parent, full)

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
