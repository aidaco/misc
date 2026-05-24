import io

import appbase


def test_root_config():
    cc = appbase.config.load(text='a=1\nb=2\n[ns]\na="string"')

    @cc.root
    class C:
        a: int
        b: int
        ns: dict
        c: int | None = None

    c = C()
    assert c.a == 1
    assert c.b == 2
    assert c.ns == {"a": "string"}


def test_config_section():
    cc = appbase.config.load(text='[ns]\na="string"')

    @cc.section("ns")
    class C:
        a: str
        b: int = 42

    assert C().a == "string"
    assert C().b == 42


def test_config_path_source(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"ns":{"a":"string"}}')
    cc = appbase.config.load(path=p)

    @cc.section("ns")
    class C:
        a: str
        b: int = 42

    assert C().a == "string"
    assert C().b == 42


def test_config_reload(tmp_path):
    cc = appbase.config.load(text='a=1\nb=2\n[ns]\nc={a=1, b=2}\nd="f"')

    @cc.root
    class C:
        a: int
        b: int

    @cc.section("ns")
    class NSC:
        c: dict
        d: str = "d"

    assert C().a == 1
    assert C().b == 2
    assert NSC().c == {"a": 1, "b": 2}
    assert NSC().d == "f"

    p = tmp_path / "config.json"
    p.write_text('{"a": 2, "b": 3, "ns":{"c":{}}}')
    cc.reload(path=p)

    assert C().a == 2
    assert C().b == 3
    assert NSC().c == {}
    assert NSC().d == "d"


def test_yaml_roundtrip_safe_and_unsafe(tmp_path):
    data = {"a": 1, "ns": {"b": "two"}}
    for fmt in ("yaml", "unsafe_yaml"):
        text = appbase.config.dump_str(data, fmt)
        assert appbase.config.read_format(io.StringIO(text), fmt) == data
        p = tmp_path / "config.out"
        appbase.config.dump_path(data, p, fmt)
        assert appbase.config.load_path(p, fmt) == data
