from tracing.getattributes import tracevar


def test_gatracevar():
    a = tracevar("a")
    b = tracevar("b").where(id=1)[1]
    c = (a + 4) ** 4
    d = (a ** 2) + (2 * (a * b)) - (b ** 2)
    assert repr(a) == "a"
    assert repr(b) == "b.where(id=1)[1]"
    assert repr(c) == "((a + 4) ** 4)"
    assert (
        repr(d)
        == "(((a ** 2) + (2 * (a * b.where(id=1)[1]))) - (b.where(id=1)[1] ** 2))"
    )
