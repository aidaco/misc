import typing
import dataclasses
import uuid
import datetime
import dateutil.parser
import pathlib
from rich import print


@dataclasses.dataclass(frozen=True, eq=True)
class TypeMap:
    pytype: typing.Type
    sqltype: str
    ser: typing.Callable = lambda o: o
    deser: typing.Callable = lambda o: o

    @classmethod
    def complete_mapping(cls, *ts):
        return {conv.pytype: conv for conv in (cls(*t) for t in ts)}


@dataclasses.dataclass(frozen=True, eq=True)
class COLUMN:
    name: str
    tm: TypeMap
    unique: bool = False
    primary: bool = False
    nullable: bool = True
    autoincrement: bool = False

    @property
    def column_def(self):
        return " ".join(
            s
            for s in [
                self.name,
                self.tm.sqltype,
                "PRIMARY KEY" if self.primary else "",
                "UNIQUE" if self.unique else "",
                "NOT NULL" if not self.nullable else "",
                "AUTOINCREMENT" if self.autoincrement else "",
            ]
            if s != ""
        )


@dataclasses.dataclass
class TABLE:
    name: str
    columns: list[COLUMN]


def as_column(field: dataclasses.Field) -> COLUMN:
    """Convert a dataclass field to a Column object."""
    column_meta = field.metadata.get("column", {})
    return COLUMN(
        name=field.name,
        tm=TYPEMAP[field.type],
        unique=column_meta.get("unique", False),
        primary=column_meta.get("primary", False),
        nullable=column_meta.get("nullable", True),
    )


def as_table(dc: typing.Type) -> TABLE:
    return TABLE(
        name=dc.__name__.lower(),
        columns=list(map(as_column, dataclasses.fields(dc))),
    )


class Statement(typing.Protocol):
    def to_sql(self) -> str:
        ...


def execute(stmt: Statement) -> typing.Any:
    sql = stmt.to_sql()
    print(sql)


class CREATE:
    def __init__(self, table: TABLE, overwrite_exists: bool = False):
        self.table = table
        self.overwrite_exists = overwrite_exists

    def to_sql(create) -> str:
        return (
            " ".join(
                s
                for s in [
                    "CREATE TABLE",
                    create.table.name,
                    f"({', '.join(c.column_def for c in create.table.columns)})",
                    "IF NOT EXISTS" if not create.overwrite_exists else "",
                ]
                if s != ""
            )
            + ";"
        )


CONFLICT_MODES = {"abort", "fail", "ignore", "replace", "rollback"}


class INSERT:
    def __init__(self, table: TABLE):
        self.table = table
        self.conflict: str | None = None
        self.values: dict[COLUMN, typing.Any] = {}

    def OR(self, conflict: str = "abort"):
        self.conflict = conflict
        return self

    def VALUES(insert, **kwargs):
        column_map = {c.name: c for c in insert.table.columns}
        insert.values = {column_map[k]: v for k, v in kwargs.items()}
        return insert

    def to_sql(insert):
        insert.values = {
            col: val
            for col, val in insert.values.items()
            if not (col.primary and not isinstance(val, col.tm.pytype))
        }
        return (
            " ".join(
                s
                for s in [
                    "INSERT",
                    f"OR {insert.conflict}"
                    if insert.conflict in CONFLICT_MODES
                    else None,
                    "INTO",
                    insert.table.name,
                    f"({', '.join(col.name for col in insert.values)})",
                    f"VALUES ({', '.join(repr(col.tm.ser(val)) for col, val in insert.values.items())})",
                ]
                if s is not None
            )
            + ";"
        )


class SELECT:
    def __init__(
        self,
        table: TABLE,
        all: bool = True,
        subset: list[str] = [],
        distinct: bool = False,
    ) -> None:
        self.table = table
        self.all = all
        self.distinct = distinct
        self.subset = subset
        self.where = None

    def WHERE(self, *args, **kwargs):
        self.where = [repr(expr) for expr in args] + [
            f"{k}={repr(v)}" for k, v in kwargs.items()
        ]
        return self

    def to_sql(select):
        return (
            " ".join(
                s
                for s in [
                    "SELECT",
                    "ALL" if select.all and not select.distinct else None,
                    "DISTINCT" if select.distinct else None,
                    "*"
                    if select.all and not select.subset
                    else f"({','.join(select.subset)})",
                    "FROM",
                    select.table.name,
                    f"WHERE {' AND '.join(select.where)}" if select.where else None,
                ]
                if s is not None
            )
            + ";"
        )


class UPDATE:
    def __init__(self, table: TABLE):
        self.table = table
        self.conflict: str | None = None
        self.where = None

    def OR(self, conflict: str = "abort") -> "UPDATE":
        self.conflict = conflict
        return self

    def SET(update, **kwargs):
        column_map = {c.name: c for c in update.table.columns}
        update.set = {column_map[k]: v for k, v in kwargs.items()}
        return update

    def WHERE(update, *args, **kwargs):
        update.where = [repr(expr) for expr in args] + [
            f"{k}={repr(v)}" for k, v in kwargs.items()
        ]
        return update

    def to_sql(update):
        return (
            " ".join(
                s
                for s in [
                    "UPDATE",
                    f"{update.table.name}",
                    f"OR {update.conflict}"
                    if update.conflict in CONFLICT_MODES
                    else None,
                    f"SET {', '.join(f'{col.name}={col.tm.ser(val)!r}' for col, val in update.set.items())}",
                    f"WHERE {' AND '.join(update.where)}" if update.where else None,
                ]
                if s is not None
            )
            + ";"
        )


TYPEMAP = TypeMap.complete_mapping(
    (type(None), "NULL"),
    (bool, "INTEGER"),
    (int, "INTEGER"),
    (str, "TEXT"),
    (float, "REAL"),
    (bytes, "BLOB"),
    (datetime.datetime, "TEXT", datetime.datetime.isoformat, dateutil.parser.parse),
    (
        datetime.timedelta,
        "REAL",
        datetime.timedelta.total_seconds,
        lambda s: datetime.timedelta(seconds=s),
    ),
    (uuid.UUID, "TEXT", lambda u: u.hex, lambda s: uuid.UUID(hex=s)),
    (pathlib.Path, "TEXT", lambda p: str(p), lambda s: pathlib.Path(s)),
)


def main():
    @dataclasses.dataclass
    class User:
        email: str
        id: int = dataclasses.field(
            default=None, metadata=dict(column={"primary": True})
        )
        created_at: datetime.datetime = dataclasses.field(
            default_factory=datetime.datetime.now
        )

    ut = as_table(User)
    u1 = User(email="test1@web.com")
    u2 = User(email="test2@web.com", id=12)
    execute(CREATE(ut))
    execute(INSERT(ut).VALUES(**dataclasses.asdict(u1)))
    execute(INSERT(ut).VALUES(**dataclasses.asdict(u2)))
    execute(SELECT(ut))
    execute(UPDATE(ut).SET(email="user@web.com").WHERE(**dataclasses.asdict(u2)))
    execute(SELECT(ut))


if __name__ == "__main__":
    main()
