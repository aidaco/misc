from misc import stateful


def test_valueproperty_basic():
    class A:
        a = stateful.ValueProperty("test value")

    inst = A()
    record = []
    inst.a.listen(record.append)
    inst.a = inst.a.value.upper()
    inst.a = "a" * 5
    print(record)
    assert record == [
        {"type": "value", "value": "test value"},
        {"type": "value", "value": "TEST VALUE"},
        {"type": "value", "value": "aaaaa"},
    ]


def test_listproperty_basic():
    class A:
        a = stateful.ListProperty(*"abcd")

    inst = A()
    record = []
    inst.a.listen(record.append)
    assert record[-1] == {"type": "value", "value": ["a", "b", "c", "d"]}
    inst.a.append("e")
    assert record[-1] == {"type": "append", "value": "e"}
    inst.a.extend("fghi")
    assert record[-1] == {"type": "extend", "values": "fghi"}
    inst.a.clear()
    assert record[-1] == {"type": "clear"}
    inst.a = [*str(456)]
    assert record[-1] == {"type": "value", "value": ["4", "5", "6"]}
    assert len(record) == 5


def test_dictproperty_basic():
    class A:
        a = stateful.DictProperty(name="john", age=68)

    inst = A()
    record = []
    inst.a.listen(record.append)
    assert record[-1] == {"type": "value", "value": {"name": "john", "age": 68}}
    inst.a["name"] = "thomas"
    assert record[-1] == {"type": "set", "key": "name", "value": "thomas"}
    del inst.a["age"]
    assert record[-1] == {"type": "delete", "key": "age", "value": 68}
    inst.a.clear()
    assert record[-1] == {"type": "clear"}
    inst.a = {"name": "alice", "age": 53}
    assert record[-1] == {"type": "value", "value": {"name": "alice", "age": 53}}
    inst.a |= {"country": "USA"}
    assert record[-1] == {"type": "update", "values": {"country": "USA"}}
    assert len(record) == 6


def test_stringproperty_basic():
    class A:
        a = stateful.StringProperty("string")

    inst = A()
    record = []
    inst.a.listen(record.append)
    assert record[-1] == {"type": "value", "value": "string"}
    inst.a += " value"
    assert record[-1] == {"type": "append", "value": " value"}
