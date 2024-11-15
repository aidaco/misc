import appbase
import pytest


def test_root_config():
    cc = appbase.config.load(text='a=1\nb=2\n[ns]\na="string"')

    @cc.root
    class c:
        a: int
        b: int
        ns: dict
        c: int | None = None

    assert c.a == 1
    assert c.b == 2
    assert c.ns == {"a": "string"}


def test_config_section():
    cc = appbase.config.load(text='[ns]\na="string"')

    @cc.section("ns")
    class c:
        a: str
        b: int = 42

    assert c.a == "string"
    assert c.b == 42


def test_config_path_source(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"ns":{"a":"string"}}')
    cc = appbase.config.load(path=p)

    @cc.section("ns")
    class c:
        a: str
        b: int = 42

    assert c.a == "string"
    assert c.b == 42
