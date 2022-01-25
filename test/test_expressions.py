import pytest
import typing
from misc import expressions as exprs


@pytest.mark.parametrize(
    "o,v",
    [
        (45, repr(45)),
        (str, repr(str)),
    ],
)
def test_encoder(o, v):
    assert exprs.encode(o) == v


def test_methodcalltrace():
    a = exprs.trace("a")
    b = (a + 4).format()
    assert exprs.encode(b) == "(a + 4).format()"
