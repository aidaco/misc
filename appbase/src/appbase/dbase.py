import dataclasses
from textwrap import dedent
from typing import (
    Callable,
    ContextManager,
    Never,
    Protocol,
    overload,
    Any,
    Iterator,
    Self,
    Annotated,
    Literal,
    TypeAlias,
    get_origin,
    get_args,
    ClassVar,
)
from dataclasses import fields, dataclass
from types import UnionType
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pydantic
import timedelta_isoformat

import sqlstmt


class DataclassLike(Protocol):
    __dataclass_fields__: ClassVar[dict]


type ModelType = pydantic.BaseModel | DataclassLike
type ConflictResolutionType = Literal["ABORT", "ROLLBACK", "FAIL", "IGNORE", "REPLACE"]
type AdapterType[T] = Callable[[T], bytes]
type ConverterType[T] = Callable[[bytes], T]
MISSING = object()
MissingType = type(MISSING)
JSONB: TypeAlias = Annotated[bytes, "jsonb"]
INTPK: TypeAlias = Annotated[int, "PRIMARY KEY"]


class StatementsType(Protocol):
    def table_name(self) -> str: ...
    def column_info(self) -> Iterator[tuple[str, type]]: ...
    def column_defs(
        self,
        type_map: dict[type | Any, str] = dict(),
    ) -> Iterator[str]: ...
    def column_def(self, name: str, cls: type, type_map: dict[type, str]) -> str: ...
    def create_table(self, strict: bool = False) -> str: ...
    def insert(
        self,
        fields: list[str] | None = None,
        conflict: ConflictResolutionType = "ABORT",
    ) -> str: ...
    def update(self, set: str, where: str) -> str: ...
    def delete(self, predicate: str = "") -> str: ...
    def count(self) -> str: ...
    def select(self, predicate: str = "") -> str: ...


TYPEADAPTER_CACHE: dict[type, pydantic.TypeAdapter] = {}


def typeadapter[M](model: type[M]) -> pydantic.TypeAdapter[M]:
    try:
        return TYPEADAPTER_CACHE[model]
    except KeyError:
        TYPEADAPTER_CACHE[model] = adapter = pydantic.TypeAdapter(model)
        return adapter


def validate[M: ModelType](
    obj: Any,
    model: type[M],
) -> M:
    if isinstance(model, pydantic.BaseModel):
        if isinstance(obj, (tuple, list)):
            obj = dict(zip(model.model_fields, obj))
        return model.model_validate(obj)
    elif dataclasses.is_dataclass(model):
        if isinstance(obj, (tuple, list)):
            obj = dict(zip((f.name for f in fields(model)), obj))
        return typeadapter(model).validate_python(obj)
    raise TypeError(f"Unsupported model type: {model}")


class EZCursor(sqlite3.Cursor):
    @overload
    def execute(self, sql: str, *params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, **params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, param: dict | tuple) -> Self: ...
    def execute(self, sql: str, *var_params, **kvar_params):
        params = sqlstmt.extract_param(var_params, kvar_params)
        return super().execute(sql, params)

    @contextmanager
    def transact(self) -> Iterator[Self]:
        try:
            self.execute("BEGIN EXCLUSIVE")
            yield self
            self.execute("COMMIT")
        except Exception as exc:
            self.execute("ROLLBACK")
            raise exc


class ParseCursor(EZCursor):
    def parseone[M: ModelType](self, model: type[M]) -> M:
        return validate(self.fetchone(), model)

    def parseall[M: ModelType](self, model: type[M]) -> list[M]:
        return list(self.parsed(model))

    def parsemany[M: ModelType](self, model: type[M], size: int | None = 1) -> list[M]:
        return [validate(row, model) for row in self.fetchmany(size)]

    def parsed[M: ModelType](self, model: type[M]) -> Iterator[M]:
        yield from (validate(row, model) for row in self)

    def query(self, model: type[ModelType]) -> sqlstmt.ModelStatements[Self]:
        return sqlstmt.sql(model, self)


class ModelCursor[M: ModelType](EZCursor):
    model: type[M]

    def fetchone(self) -> M:
        return validate(super().fetchone(), self.model)

    def fetchall(self) -> list[M]:
        return list(self)

    def fetchmany(self, size: int | None = 1) -> list[M]:
        return [validate(row, self.model) for row in super().fetchmany(size)]

    def query(self) -> sqlstmt.ModelStatements[Self]:
        return sqlstmt.sql(self.model, self)

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> M:
        return validate(super().__next__(), self.model)


class Repository:
    def __init__(self, connection: sqlite3.Connection | None = None) -> None:
        self.connection: sqlite3.Connection | None = connection

    def connect(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def cursor(self) -> ParseCursor:
        assert self.connection is not None
        return self.connection.cursor(ParseCursor)  # type: ignore

    def transact(self) -> ContextManager[ParseCursor]:
        return self.cursor().transact()

    def execute(self, sql, *var_params, **kw_params) -> ParseCursor:
        return self.cursor().execute(sql, *var_params, **kw_params)

    def query(self, model: type[ModelType]) -> sqlstmt.ModelStatements[ParseCursor]:
        return self.cursor().query(model)


class __ModelStatements:
    def table_name(self) -> str: ...
    def column_info(self) -> Iterator[tuple[str, type]]: ...

    def column_defs(
        self,
        type_map: dict[type | Any, str] = {
            str: "TEXT",
            int: "INTEGER",
            float: "REAL",
            bytes: "BLOB",
            datetime: "DATETIME",
            timedelta: "TIMEDELTA",
            Path: "PATH",
            JSONB: "JSONB",
        },
    ) -> Iterator[str]:
        for name, cls in self.column_info():
            yield self.column_def(name, cls, type_map)

    def column_def(self, name: str, cls: type, type_map: dict[type, str]) -> str:
        sqlite_type = None
        constraints = None
        not_null = True

        def unpack_type(t):
            nonlocal sqlite_type, not_null, constraints
            try:
                sqlite_type = type_map[t]
                return
            except KeyError:
                pass
            origin = get_origin(t)
            if origin is Annotated:
                match get_args(t):
                    case (_type, _def):
                        constraints = _def
                        unpack_type(_type)
                        return
                    case _:
                        raise TypeError(f"Can only accept one str annotation: {t}")
            elif origin is UnionType:
                match get_args(t):
                    case (_type, None) | (None, _type):
                        not_null = False
                        unpack_type(_type)
                        return
                    case _:
                        raise TypeError(f"Unions not supported, except | None: {t}")

        unpack_type(cls)
        parts = [name, sqlite_type, "NOT NULL" if not_null else None, constraints]
        return " ".join(p for p in parts if p)

    def create_table(self, strict: bool = False) -> str:
        table = self.table_name()
        columns = ", ".join(self.column_defs())
        parts = [f"CREATE TABLE IF NOT EXISTS {table}({columns})"]
        if strict:
            parts.append("STRICT")
        return " ".join(parts) + ";"

    def insert(
        self,
        fields: list[str] | None = None,
        conflict: ConflictResolutionType = "ABORT",
    ) -> str:
        table = self.table_name()
        if fields is not None:
            names = fields
            placeholders = ", ".join(f":{name}" for name in names)
        else:
            names = [name for name, _ in self.column_info()]
            placeholders = ", ".join("?" for _ in names)

        columns = ", ".join(names)
        return f"INSERT OR {conflict} INTO {table}({columns}) VALUES ({placeholders}) RETURNING *;"

    def update(self, set: str, where: str) -> str:
        return f"UPDATE {self.table_name()} SET {set} WHERE {where} RETURNING *"

    def delete(self, predicate: str = "") -> str:
        return f"DELETE FROM {self.table_name()} {predicate} RETURNING *;"

    def count(self) -> str:
        table = self.table_name()
        return f"SELECT COUNT(*) FROM {table}"

    def select(self, predicate: str = "") -> str:
        table = self.table_name()
        columns = ", ".join(name for name, _ in self.column_info())
        return f"SELECT {columns} FROM {table} {predicate};"


class Table[M: ModelType]:
    def __init__(
        self,
        model: type[M],
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self.connection: sqlite3.Connection | None = connection
        self.model: type[M] = model

    def connect(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.create_table()

    def cursor(self) -> ModelCursor[M]:
        assert self.connection is not None
        cursor = self.connection.cursor(ModelCursor)  # type: ignore
        cursor.model = self.model
        return cursor

    def execute(self, sql: str, *params: Any, **kwparams: Any) -> ModelCursor[M]:
        return self.cursor().execute(sql, *params, **kwparams)

    def sql(self) -> sqlstmt.ModelStatements[Never]:
        return sqlstmt.sql(self.model)

    def query(self) -> sqlstmt.ModelStatements[ModelCursor[M]]:
        return self.cursor().query()

    def transact(self) -> ContextManager[ModelCursor[M]]:
        return self.cursor().transact()

    def create_table(self) -> None:
        self.query().create().if_not_exists().execute()


ADAPTERS: dict[type, AdapterType] = {
    datetime: lambda dt: dt.astimezone(timezone.utc).isoformat().encode(),
    Path: Path.__bytes__,
    timedelta: lambda td: timedelta_isoformat.timedelta.isoformat(td).encode(),
}
CONVERTERS: dict[str, ConverterType] = {
    "datetime": lambda b: datetime.fromisoformat(b.decode()),
    "path": lambda b: Path(b.decode()),
    "timedelta": lambda b: timedelta_isoformat.timedelta.fromisoformat(b.decode()),
}


@contextmanager
def connect(
    uri: str | Path,
    /,
    autocommit: bool = True,
    detect_types: int = sqlite3.PARSE_DECLTYPES,
    timeout: int = 30,
    echo: bool = True,
    adapters: dict[type, AdapterType] = ADAPTERS,
    converters: dict[str, ConverterType] = CONVERTERS,
    **kwargs,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        uri,
        autocommit=autocommit,
        detect_types=detect_types,
        timeout=timeout,
        **kwargs,
    )
    _initialize_connection(connection, echo, adapters, converters)
    try:
        yield connection
    finally:
        _finalize_connection(connection)
        connection.close()


def _initialize_connection(
    connection: sqlite3.Connection,
    echo: bool,
    adapters: dict[type, AdapterType],
    converters: dict[str, ConverterType],
) -> None:
    if echo:
        connection.set_trace_callback(print)
    for cls, adapter in adapters.items():
        sqlite3.register_adapter(cls, adapter)
    for name, converter in converters.items():
        sqlite3.register_converter(name, converter)
    connection.executescript(
        dedent("""\
        PRAGMA journal_mode = wal;
        PRAGMA synchronous = normal;
        PRAGMA temp_store = memory;
        PRAGMA mmap_size = 30000000000;
        PRAGMA cache_size = -32000;
        PRAGMA foreign_keys = on;
        PRAGMA auto_vacuum = incremental;
        PRAGMA foreign_keys = on;
        PRAGMA secure_delete = on;
        PRAGMA optimize = 0x10002;
    """)
    )


def _finalize_connection(connection: sqlite3.Connection) -> None:
    connection.executescript(
        dedent("""\
        VACUUM;
        PRAGMA analysis_limit=400;
        PRAGMA optimize;
    """)
    )
