import typing
import dataclasses


class GuardType:
    ...


PassthroughGuard = GuardType()
UnaryGuard = GuardType()


@dataclasses.dataclass
class Expression:
    operands: list[typing.Any]
    operator: str | GuardType = PassthroughGuard

    @classmethod
    def trace(cls, op, expr_cls=None):
        expr_cls = expr_cls or cls

        def __op__(self, *args):
            opers = [self] if not args else [self, *args]
            return expr_cls(opers, op)

        setattr(cls, f"__{op}__", __op__)

    def __repr__(self):
        ...


class VariableExpression(Expression):
    def __repr__(self):
        return str(self.operands[0])


class PrefixExpression(Expression):
    def __repr__(self):
        exp = "".join(
            s
            for s in [
                self.operator if self.operator is not PassthroughGuard else None,
                f"{' '.join(repr(o) for o in self.operands)}",
            ]
            if s is not None
        )
        return f"({exp})"


class InfixExpression(Expression):
    def __repr__(self):
        exp = " ".join(
            s
            for s in [
                repr(self.operands[0]),
                SYMBOL_MAP[self.operator]
                if self.operator is not PassthroughGuard
                else None,
                repr(self.operands[1]) if len(self.operands) > 1 else None,
            ]
            if s is not None
        )
        return f"({exp})"


class CallExpression(Expression):
    def __repr__(self):
        exp = "".join(
            s
            for s in [
                repr(self.operands[0]),
                f"({', '.join(repr(o) for o in self.operands[1:])})",
            ]
            if s is not None
        )
        return f"{exp}"


class GetAttrExpression(Expression):
    def __repr__(self):
        exp = ""
        for op in self.operands:
            exp += f"{op}"
        op = SYMBOL_MAP[self.operator]
        op = op if isinstance(op, str) else op[0]
        exp = "".join(
            s
            for s in [
                str(self.operands[0]),
                op,
                str(self.operands[1]),
            ]
            if s is not None
        )
        return f"({exp})"


def expression(value: str) -> Expression:
    return VariableExpression([value])


SYMBOL_MAP = {
    "lt": "<",
    "le": "<=",
    "eq": "==",
    "ne": "!=",
    "ge": ">=",
    "gt": ">",
    "not": ("NOT", PrefixExpression),
    "add": "+",
    "and": "AND",
    "truediv": "/",
    "floordiv": "//",
    "invert": ("~", PrefixExpression),
    "mod": "%",
    "mul": "*",
    "or": "|",
    "pow": "**",
    "sub": "-",
    "xor": "^",
    "contains": "in",
    "getattr": (".", GetAttrExpression),
    "call": ("()", CallExpression),
}

for o, val in SYMBOL_MAP.items():
    if isinstance(val, tuple):
        Expression.trace(o, val[1])
    else:
        Expression.trace(o, InfixExpression)
