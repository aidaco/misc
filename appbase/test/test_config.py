import appbase


def test_root_config():
    src = appbase.config.StrSource('a=1\nb=2\n[ns]\na="string"', "toml")
    cc = appbase.config.load(src)

    @cc.root
    class c:
        a: int
        b: int
        ns: dict
        c: int | None = None

    assert c.a == 1
    assert c.b == 2
    assert c.ns == {"a": "string"}
