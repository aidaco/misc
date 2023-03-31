from functools import reduce


def passthrough(obj):
    return obj


def compose(f, g):
    return lambda *args, **kwargs: g(f(*args, **kwargs))


def composed(*functions):
    return reduce(compose, functions, passthrough)


class monad:
    def __init__(self, value):
        self.value = value

    def bind(self, fn):
        return monad(fn(self.value))

    def unpack(self):
        return self.value

    def __rshift__(self, fn):
        return self.bind(fn)

    def __call__(self, *args, **kwargs):
        return self.unpack(*args, **kwargs)


class pipeline(monad):
    def bind(self, fn):
        return pipeline(lambda *args, **kwargs: fn(self.value(*args, **kwargs)))

    def unpack(self, *args, **kwargs):
        return self.value(*args, **kwargs)


class promise(monad):
    def bind(self, fn):
        return promise(lambda s, f: self.value(composed(s, fn), f))

    def err(self, fn):
        return promise(lambda s, f: self.value(s, composed(f, fn)))

    def unpack(self, *args, **kwargs):
        return self.value(passthrough, passthrough)(*args, **kwargs)


def attempt(fn):
    def resolve(success, failure):
        def do(*args, **kwargs):
            try:
                return success(fn(*args, **kwargs))
            except Exception as error:
                return failure(error)

        return do

    return promise(resolve)


def main():
    def fake_load_user(id, err=False):
        raise ValueError("Sometimes operations fail!")

    a = pipeline(str.strip) >> str.upper >> set
    lastupper = (
        attempt(lambda xs: xs[-1])
        .bind(str.upper)
        .err(lambda error: f"Failed with {error=}")
    )
    print(
        *enumerate(
            (
                a("  hello world  "),
                attempt(passthrough)(31),
                lastupper(["hello", "world"]),
                lastupper([]),
                attempt(fake_load_user)(31),
            )
        ),
        sep="\n",
    )


if __name__ == "__main__":
    main()
