import typing


class Operator:
    ...

class Operand:
    ...

@typing.runtime_checkable
class Operation(typing.Protocol):
    operator: Operator
    operand: Operand

class MethodCallArguments(Operand):
    obj: typing.Any
    method: str
    args: Arguments

class MethodCall(Operation):
    ...
