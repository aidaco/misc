import typing
from dataclasses import dataclass


@dataclass
class Named:
    name: str


def _capture_unary(name: str):
    def _capture(self, other):
        print(self, name, other)
        return UnaryOp(name, self)

    return _capture


def _capture_binary(name: str):
    def _capture(self, other):
        print(self, name, other)
        return BinaryOp(name, self, other)

    return _capture


class ExpressionCapture:
    __not__ = _capture_unary("not")
    __and__ = _capture_binary("and")
    __lt__ = _capture_binary("<")
    __le__ = _capture_binary("<=")
    __gt__ = _capture_binary(">")
    __ge__ = _capture_binary(">=")

    __add__ = _capture_binary("+")
    __sub__ = _capture_binary("-")
    __mul__ = _capture_binary("*")
    __div__ = _capture_binary("/")


@dataclass
class UnaryOp(ExpressionCapture, Named):
    operand: typing.Any

    def __repr__(self):
        return f"{self.name}{self.operand!r}"


@dataclass
class BinaryOp(ExpressionCapture, Named):
    left: typing.Any
    right: typing.Any

    def __repr__(self):
        return f"{self.left!r} {self.name} {self.right!r}"


@dataclass
class FieldInfo(ExpressionCapture):
    schema: "SchemaInfo"
    name: str
    type: typing.Type

    def __repr__(self):
        return f"{self.schema.name}.{self.name}"


@dataclass
class SchemaInfo:
    name: str
    fields: tuple[FieldInfo] = ()


class SchemaMeta(type):
    def __new__(cls, name, bases, namespace) -> SchemaInfo:
        obj = super().__new__(cls, name, bases, namespace)
        obj.__schema__ = schema = SchemaInfo(name.lower() + "s")
        schema.fields = tuple(
            FieldInfo(schema, n, t)
            for n, t in namespace.get("__annotations__", {}).items()
        )
        for field in schema.fields:
            setattr(obj, field.name, field)
        return obj


class Schema(metaclass=SchemaMeta):
    ...
