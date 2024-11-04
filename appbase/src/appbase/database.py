from textwrap import dedent
from typing import (
    Callable,
    ContextManager,
    Protocol,
    overload,
    Any,
    Iterator,
    Self,
    Annotated,
    Literal,
    TypeAlias,
    ClassVar,
    runtime_checkable,
)
from dataclasses import fields
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pydantic
import timedelta_isoformat

import appbase.statements


@runtime_checkable
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


TYPEADAPTER_CACHE: dict[type, pydantic.TypeAdapter] = {}


def typeadapter[M](model: type[M]) -> pydantic.TypeAdapter[M]:
    try:
        return TYPEADAPTER_CACHE[model]
    except KeyError:
        TYPEADAPTER_CACHE[model] = adapter = pydantic.TypeAdapter(model)
        return adapter


def validate[M](
    obj: Any,
    model: type[M],
) -> M:
    if isinstance(model, pydantic.BaseModel):
        if isinstance(obj, (tuple, list)):
            obj = dict(zip(model.model_fields, obj))
        return model.model_validate(obj)
    elif isinstance(model, DataclassLike):
        if isinstance(obj, (tuple, list)):
            obj = dict(zip((f.name for f in fields(model)), obj))
    return typeadapter(model).validate_python(obj)


class EZCursor(sqlite3.Cursor):
    @overload
    def execute(self, sql: str, *params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, **params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, param: dict | tuple) -> Self: ...
    def execute(self, sql: str, *var_params, **kvar_params):
        params = appbase.statements.extract_param(var_params, kvar_params)
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

    def parseone[M](self, model: type[M]) -> M:
        return validate(self.fetchone(), model)

    def parseall[M](self, model: type[M]) -> list[M]:
        return list(self.parsed(model))

    def parsemany[M](self, model: type[M], size: int | None = 1) -> list[M]:
        return [validate(row, model) for row in self.fetchmany(size)]

    def parsed[M](self, model: type[M]) -> Iterator[M]:
        yield from (validate(row, model) for row in self)


class ModelCursor[M](EZCursor):
    model: type[M]

    def one(self) -> M:
        return super().parseone(self.model)

    def all(self) -> list[M]:
        return super().parseall(self.model)

    def many(self, size: int | None = 1) -> list[M]:
        return super().parsemany(self.model, size)

    def iter(self) -> Iterator[M]:
        yield from super().parsed(self.model)


class Repository:
    def __init__(self, connection: sqlite3.Connection | None = None) -> None:
        self.connection: sqlite3.Connection | None = connection

    def cursor(self, connection: sqlite3.Connection | None = None) -> EZCursor:
        connection = connection or self.connection
        if connection is None:
            raise ValueError("Must pass in a connection or cursor at some point.")
        return connection.cursor(EZCursor)  # type: ignore

    def execute(
        self,
        sql: str,
        *params,
        connection: sqlite3.Connection | None = None,
        **kwparams,
    ) -> EZCursor:
        return self.cursor(connection).execute(sql, *params, **kwparams)

    def transact(
        self, connection: sqlite3.Connection | None = None
    ) -> ContextManager[EZCursor]:
        return self.cursor(connection).transact()


class Table[M: ModelType]:
    def __init__(
        self, model: type[M] | None = None, connection: sqlite3.Connection | None = None
    ) -> None:
        if model:
            self.model: type[M] = model
        elif not hasattr(self, "model"):
            raise ValueError("Must pass a model or set on subclass.")

        self.connection: sqlite3.Connection | None = connection

    def cursor(self, connection: sqlite3.Connection | None = None) -> ModelCursor[M]:
        assert self.model is not None
        connection = connection or self.connection
        if connection is None:
            raise ValueError("Must pass in a connection or cursor at some point.")
        cursor = connection.cursor(ModelCursor)  # type: ignore
        cursor.model = self.model
        return cursor

    def ex(
        self,
        sql: str,
        *params,
        connection: sqlite3.Connection | None = None,
        **kwparams,
    ) -> ModelCursor[M]:
        return self.cursor(connection).execute(sql, *params, **kwparams)

    def tx(
        self, connection: sqlite3.Connection | None = None
    ) -> ContextManager[ModelCursor[M]]:
        return self.cursor(connection).transact()

    def delete(self) -> appbase.statements.Delete[ModelCursor[M]]:
        return appbase.statements.delete(self.model, cursor=self.cursor())

    def count(self) -> appbase.statements.Count[ModelCursor[M]]:
        return appbase.statements.count(self.model, cursor=self.cursor())

    def create(self) -> appbase.statements.Create[ModelCursor[M]]:
        return appbase.statements.create(self.model, cursor=self.cursor())

    def insert(self) -> appbase.statements.Insert[ModelCursor[M]]:
        return appbase.statements.insert(self.model, cursor=self.cursor())

    def select(self) -> appbase.statements.Select[ModelCursor[M]]:
        return appbase.statements.select(self.model, cursor=self.cursor())

    def update(self) -> appbase.statements.Update[ModelCursor[M]]:
        return appbase.statements.update(self.model, cursor=self.cursor())


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
        autocommit=autocommit,  # type: ignore
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
