import dataclasses
import datetime
import pathlib
import typing
import uuid

import dateutil.parser
from rich import print


@dataclasses.dataclass(frozen=True, eq=True)
class TypeMap:
    pytype: typing.Type
    sqltype: str
    def ser(o):
        return o
    def deser(o):
        return o

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

    @property
    def column_map(self):
        return dict((c.name, c) for c in self.columns)


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


@dataclasses.dataclass
class CREATE:
    table: TABLE
    overwrite: bool = False

    def OVERWRITEOK(create):
        create.overwrite = True
        return create

    def to_sql(create) -> str:
        return (
            " ".join(
                s
                for s in [
                    "CREATE TABLE",
                    create.table.name,
                    f"({', '.join(map(lambda c: c.column_def, create.table.columns))})",
                    "IF NOT EXISTS" if not create.overwrite else None,
                ]
                if s is not None
            )
            + ";"
        )


CONFLICT_MODES = {"abort", "fail", "ignore", "replace", "rollback"}


@dataclasses.dataclass
class INSERT:
    table: TABLE
    conflict: str = "abort"
    values: dict[COLUMN, typing.Any] = dataclasses.field(default_factory=dict)

    def OR(insert, conflict: str = "abort"):
        insert.conflict = conflict
        return insert

    def VALUES(insert, dc: typing.Any = None, **kwargs):
        if dc and dataclasses.is_dataclass(dc) and type(dc) != type:
            insert.values = {
                insert.table.column_map[k]: v for k, v in dataclasses.asdict(dc).items()
            }
        else:
            insert.values = {insert.table.column_map[k]: v for k, v in kwargs.items()}
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
                    f"OR {insert.conflict.upper()}"
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


@dataclasses.dataclass(init=False)
class SELECT:
    table: TABLE
    all: bool = True
    distinct: bool = False
    subset: list[COLUMN] = dataclasses.field(default_factory=list)
    where: dict[COLUMN, typing.Any] = dataclasses.field(default_factory=dict)

    def __init__(select, table: TABLE, *subset: COLUMN):
        select.table = table
        select.subset = list(subset)
        select.where = {}

    def DISTINCT(select, *subset: COLUMN):
        select.subset = list(subset)
        select.distinct = True
        select.all = False

    def WHERE(select, dc: typing.Any = None, *exprs, **colexprs):
        if dc and dataclasses.is_dataclass(dc) and type(dc) != type:
            select.where = {
                select.table.column_map[k]: v for k, v in dataclasses.asdict(dc).items()
            }
        else:
            colvals = {select.table.column_map[k]: v for k, v in colexprs.items()}
            select.where = colvals | {
                select.table.column_map[k]: v
                for k, v in select.table.column_map.items()
                if select.table.column_map[k] not in colvals
            }
        return select

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


@dataclasses.dataclass
class UPDATE:
    table: TABLE
    conflict: str = "abort"
    where: dict[COLUMN, typing.Any] = dataclasses.field(default_factory=dict)

    def OR(update, conflict: str) -> "UPDATE":
        update.conflict = conflict
        return update

    def SET(update, dc: typing.Any = None, **colvals: typing.Any):
        if dc and dataclasses.is_dataclass(dc) and type(dc) != type:
            update.set = {
                update.table.column_map[k]: v for k, v in dataclasses.asdict(dc).items()
            }
        else:
            update.set = {update.table.column_map[c]: v for c, v in colvals.items()}
        return update

    def WHERE(update, dc: typing.Any = None, *exprs, **colexprs):
        if dc and dataclasses.is_dataclass(dc) and type(dc) != type:
            update.where = {
                update.table.column_map[k]: v for k, v in dataclasses.asdict(dc).items()
            }
        else:
            colvals = {update.table.column_map[k]: v for k, v in colexprs.items()}
            update.where = colvals | {
                update.table.column_map[k]: v
                for k, v in update.table.column_map.items()
                if update.table.column_map[k] not in colvals
            }
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
                    f"SET {', '.join(f'{c.name}={c.tm.ser(v)!r}' for c,v in update.set.items())}",
                    f"WHERE {' AND '.join(f'{col.name}={col.tm.ser(val)!r}' for col, val in update.where.items())}"
                    if update.where
                    else None,
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
        email: str = dataclasses.field(metadata=dict(column={"unique": True}))
        id: int = dataclasses.field(
            default=None, metadata=dict(column={"primary": True})
        )
        created_at: datetime.datetime = dataclasses.field(
            default_factory=datetime.datetime.now
        )

    users = as_table(User)
    u1 = User(email="test@web.com")
    u2 = User(email="test@web.com", id=12)
    execute(CREATE(users))
    execute(INSERT(users).VALUES(u1))
    try:
        execute(INSERT(users).VALUES(u2))
    except Exception as e:
        print(e)
    execute(UPDATE(users).SET(email="user@web.com").WHERE(u2))
    execute(INSERT(users).VALUES(u2))
    execute(SELECT(users))


if __name__ == "__main__":
    main()
