from textwrap import dedent
from typing import (
    Callable,
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
from dataclasses import fields, is_dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PosixPath, WindowsPath
import sqlite3

import pydantic
import timedelta_isoformat

from appbase import statements


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
    validator: Callable[[Any], M]
    if isinstance(model, pydantic.BaseModel):
        validator = model.model_validate
        field_names = iter(model.model_fields)
    elif isinstance(model, DataclassLike):
        validator = typeadapter(model).validate_python  # type: ignore
        field_names = (f.name for f in fields(model))
    else:
        raise TypeError(f"Unsupported model type: {model}")

    if isinstance(obj, (tuple, list)):
        obj = dict(zip(field_names, obj))
    elif isinstance(obj, sqlite3.Row):
        obj = dict(obj)

    return validator(obj)  # type: ignore


class CursorBase(sqlite3.Cursor):
    @overload
    def execute(self, sql: statements.Statement) -> Self: ...
    @overload
    def execute(self, sql: str, *params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, **params: Any) -> Self: ...
    @overload
    def execute(self, sql: str, param: dict | tuple) -> Self: ...
    def execute(self, sql, *var_params, **kvar_params):
        if isinstance(sql, statements.Statement) and (
            exec := getattr(sql, "execute", None)
        ):
            return exec(self)
        else:
            params = statements.extract_param(var_params, kvar_params)
            return super().execute(str(sql), params)

    @contextmanager
    def transact(self) -> Iterator[Self]:
        try:
            self.execute("BEGIN EXCLUSIVE")
            yield self
            self.execute("COMMIT")
        except Exception as exc:
            self.execute("ROLLBACK")
            raise exc

    def parsen(self, *types: type) -> Iterator:
        row = self.fetchone()
        match row:
            case sqlite3.Row:
                row = (row[k] for k in row)
            case tuple():
                row = iter(row)
        for typ in types:
            match typ:
                case type() if is_dataclass(typ):
                    ns = (f.name for f in fields(typ))
                    val = dict(zip(ns, row))
                    yield typeadapter(typ).validate_python(val)
                case type() if issubclass(typ, pydantic.BaseModel):
                    ns = iter(typ.model_fields)
                    val = dict(zip(ns, row))
                    yield typeadapter(typ).validate_python(val)
                case type():
                    val = next(row)
                    yield typeadapter(typ).validate_python(val)
                case _:
                    raise TypeError(f"Unsupported type {typ}.")

    def parseone[M](self, model: type[M]) -> M | None:
        row = self.fetchone()
        return row if row is None else validate(row, model)

    def parseall[M](self, model: type[M]) -> list[M]:
        return list(self.parsed(model))

    def parsemany[M](self, model: type[M], size: int | None = 1) -> list[M]:
        return [validate(row, model) for row in self.fetchmany(size)]

    def parsed[M](self, model: type[M]) -> Iterator[M]:
        yield from (validate(row, model) for row in self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc, exc_type, exc_tb) -> None:
        self.close()


class EZCursor(CursorBase):
    def delete(
        self,
        model: type,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> statements.Delete[Self]:
        return statements.Delete.from_model(self, model, where, returning)

    def count(self, model: type) -> statements.Count[Self]:
        return statements.Count.from_model(self, model)

    def create(
        self,
        model: type,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> statements.Create[Self]:
        return statements.Create.from_model(
            self,
            model=model,
            if_not_exists=if_not_exists,
            strict=strict,
            without_rowid=without_rowid,
        )

    def insert(
        self,
        model: type,
        conflict_resolution: ConflictResolutionType | None = None,
        columns: list[str] | None = None,
        values: list[str] | None = None,
        returning: list[str] | None = None,
    ) -> statements.Insert[Self]:
        return statements.Insert.from_model(
            self,
            model=model,
            conflict_resolution=conflict_resolution,
            columns=columns,
            values=values,
            returning=returning,
        )

    def select(
        self,
        model: type,
        fields: list[str | type] | None = None,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> statements.Select[Self]:
        return statements.Select.from_model(
            self,
            model=model,
            fields=fields,
            where=where,
            offset=offset,
            limit=limit,
            orderby=orderby,
        )

    def update(
        self,
        model: type,
        conflict_resolution: ConflictResolutionType | None = None,
        set: str | None = None,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> statements.Update[Self]:
        return statements.Update.from_model(
            cursor=self,
            model=model,
            conflict_resolution=conflict_resolution,
            set=set,
            where=where,
            returning=returning,
        )


class ModelCursor[M](CursorBase):
    model: type[M]

    def one(self) -> M | None:
        return super().parseone(self.model)

    def all(self) -> list[M]:
        return super().parseall(self.model)

    def many(self, size: int | None = 1) -> list[M]:
        return super().parsemany(self.model, size)

    def iter(self) -> Iterator[M]:
        yield from super().parsed(self.model)

    def delete(
        self,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> statements.Delete[Self]:
        return statements.Delete.from_model(self, self.model, where, returning)

    def count(self) -> statements.Count[Self]:
        return statements.Count.from_model(self, self.model)

    def create(
        self,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> statements.Create[Self]:
        return statements.Create.from_model(
            self,
            model=self.model,
            if_not_exists=if_not_exists,
            strict=strict,
            without_rowid=without_rowid,
        )

    def insert(
        self,
        conflict_resolution: ConflictResolutionType | None = None,
        columns: list[str] | None = None,
        values: list[str] | None = None,
        returning: list[str] | None = None,
    ) -> statements.Insert[Self]:
        return statements.Insert.from_model(
            self,
            model=self.model,
            conflict_resolution=conflict_resolution,
            columns=columns,
            values=values,
            returning=returning,
        )

    def select(
        self,
        fields: list[str | type] | None = None,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> statements.Select[Self]:
        return statements.Select.from_model(
            self,
            model=self.model,
            fields=fields,
            where=where,
            offset=offset,
            limit=limit,
            orderby=orderby,
        )

    def update(
        self,
        conflict_resolution: ConflictResolutionType | None = None,
        set: str | None = None,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> statements.Update[Self]:
        return statements.Update.from_model(
            cursor=self,
            model=self.model,
            conflict_resolution=conflict_resolution,
            set=set,
            where=where,
            returning=returning,
        )


class Table[M: ModelType]:
    def __init__(self, model: type[M] | None = None) -> None:
        if model:
            self.model: type[M] = model
        elif not hasattr(self, "model"):
            raise ValueError("Must pass a model or set on subclass.")

    def cursor(self, connection: sqlite3.Connection) -> ModelCursor[M]:
        assert self.model is not None
        cursor = connection.cursor(ModelCursor)  # type: ignore
        cursor.model = self.model
        return cursor


class EZConnection(sqlite3.Connection):
    def table[M: ModelType](self, model: type[M]) -> ModelCursor[M]:
        cursor = super().cursor(ModelCursor)
        cursor.model = model
        return cursor

    def cursor[C: sqlite3.Cursor](self, factory: type[C] = EZCursor) -> C:  # type: ignore[override]
        return super().cursor(factory)


ADAPTERS: dict[type, AdapterType] = {
    datetime: lambda dt: dt.astimezone(timezone.utc).isoformat().encode(),
    Path: Path.__bytes__,
    PosixPath: PosixPath.__bytes__,
    WindowsPath: WindowsPath.__bytes__,
    timedelta: lambda td: timedelta_isoformat.timedelta.isoformat(td).encode(),
}
CONVERTERS: dict[str, ConverterType] = {
    "datetime": lambda b: datetime.fromisoformat(b.decode()),
    "path": lambda b: Path(b.decode()),
    "timedelta": lambda b: timedelta_isoformat.timedelta.fromisoformat(b.decode()),
}


def connect[C: sqlite3.Connection](
    uri: str | Path,
    /,
    autocommit: bool = True,
    detect_types: int = sqlite3.PARSE_DECLTYPES,
    timeout: int = 30,
    echo: bool = True,
    adapters: dict[type, AdapterType] = ADAPTERS,
    converters: dict[str, ConverterType] = CONVERTERS,
    factory: type[C] = EZConnection,
    **kwargs,
) -> C:
    connection = sqlite3.connect(
        uri,
        autocommit=autocommit,  # type: ignore
        detect_types=detect_types,
        timeout=timeout,
        factory=factory,
        **kwargs,
    )

    _initialize_connection(
        connection, echo=echo, adapters=adapters, converters=converters
    )
    return connection


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


@contextmanager
def lifespan[C: sqlite3.Connection](
    uri: str | Path,
    /,
    autocommit: bool = True,
    detect_types: int = sqlite3.PARSE_DECLTYPES,
    timeout: int = 30,
    echo: bool = True,
    adapters: dict[type, AdapterType] = ADAPTERS,
    converters: dict[str, ConverterType] = CONVERTERS,
    factory: type[C] = EZConnection,
    **kwargs,
) -> Iterator[C]:
    connection = connect(
        uri,
        autocommit=autocommit,
        detect_types=detect_types,
        timeout=timeout,
        echo=echo,
        adapters=adapters,
        converters=converters,
        factory=factory,
        **kwargs,
    )
    try:
        yield connection
    finally:
        _finalize_connection(connection)
        connection.close()
