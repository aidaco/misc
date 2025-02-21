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
from dataclasses import dataclass, fields, is_dataclass, field
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

    def varparseone(self, *types: type) -> tuple:
        row = self.fetchone()
        match row:
            case sqlite3.Row:
                row = (row[k] for k in row)
            case tuple():
                row = iter(row)
        result = ()
        for typ in types:
            match typ:
                case type() if is_dataclass(typ):
                    ns = (f.name for f in fields(typ))
                    val = dict(zip(ns, row))
                    result = (*result, typeadapter(typ).validate_python(val))
                case type() if issubclass(typ, pydantic.BaseModel):
                    ns = iter(typ.model_fields)
                    val = dict(zip(ns, row))
                    result = (*result, typeadapter(typ).validate_python(val))
                case type():
                    val = next(row)
                    result = (*result, typeadapter(typ).validate_python(val))
                case _:
                    raise TypeError(f"Unsupported type {typ}.")
        return result

    def varparseall(self, *types: type) -> list[tuple]:
        return list(self.varparsed(*types))

    def varparsed(self, *types: type) -> Iterator[tuple]:
        for row in self:
            match row:
                case sqlite3.Row:
                    row = (row[k] for k in row)
                case tuple():
                    row = iter(row)
            result = ()
            for typ in types:
                match typ:
                    case type() if is_dataclass(typ):
                        ns = (f.name for f in fields(typ))
                        val = dict(zip(ns, row))
                        result = (*result, typeadapter(typ).validate_python(val))
                    case type() if issubclass(typ, pydantic.BaseModel):
                        ns = iter(typ.model_fields)
                        val = dict(zip(ns, row))
                        result = (*result, typeadapter(typ).validate_python(val))
                    case type():
                        val = next(row)
                        result = (*result, typeadapter(typ).validate_python(val))
                    case _:
                        raise TypeError(f"Unsupported type {typ}.")
            yield result

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
        model_or_name: str | type,
        /,
        name: str | None = None,
        constraints: list[str] | None = None,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> statements.Create[Self]:
        return statements.create(
            self,
            model_or_name,
            name=name,
            constraints=constraints,
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
        *fields: str | type,
        table: str | type | None = None,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> statements.Select[Self]:
        return statements.select(
            self,
            *fields,
            table=table,
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
        name: str | None = None,
        constraints: list[str] | None = None,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> statements.Create[Self]:
        return statements.create(
            self,
            self.model,
            name=name,
            constraints=constraints,
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
        *fields: str | type,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> statements.Select[Self]:
        return statements.select(
            self,
            *(fields or (self.model,)),
            table=self.model,
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


@dataclass
class Database:
    uri: str | Path
    autocommit: bool = True
    detect_types: int = sqlite3.PARSE_DECLTYPES
    timeout: int = 30
    echo: bool = False
    adapters: dict[type, AdapterType] = field(default_factory=ADAPTERS.copy)
    converters: dict[str, ConverterType] = field(default_factory=CONVERTERS.copy)

    connection: sqlite3.Connection | None = None

    def table[M: ModelType](self, model: type[M]) -> ModelCursor[M]:
        cursor = self.cursor(ModelCursor)
        cursor.model = model
        return cursor

    def cursor[C: sqlite3.Cursor](self, factory: type[C] = EZCursor) -> C:
        return self.connect().cursor(factory)

    def connect(self) -> sqlite3.Connection:
        if self.connection is None:
            if isinstance(self.uri, Path):
                self.uri.parent.mkdir(parents=True, exist_ok=True)
            self.connection = connect_raw(
                uri=self.uri,
                autocommit=self.autocommit,
                detect_types=self.detect_types,
                timeout=self.timeout,
                echo=self.echo,
                adapters=self.adapters,
                converters=self.converters,
            )
        return self.connection

    def close(self) -> None:
        if self.connection is not None:
            close_raw(self.connection)

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc, exc_type, exc_tb) -> None:
        self.close()


def connect_raw(
    uri: str | Path,
    autocommit: bool,
    detect_types: int,
    timeout: int,
    echo: bool,
    adapters: dict[type, AdapterType],
    converters: dict[str, ConverterType],
) -> sqlite3.Connection:
    connection = sqlite3.connect(
        uri,
        autocommit=autocommit,
        detect_types=detect_types,
        timeout=timeout,
    )
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
        PRAGMA secure_delete = on;
        PRAGMA optimize = 0x10002;
        PRAGMA recursive_triggers = on;
    """)
    )
    return connection


def close_raw(connection: sqlite3.Connection) -> None:
    connection.executescript(
        dedent("""\
        VACUUM;
        PRAGMA analysis_limit=400;
        PRAGMA optimize;
    """)
    )
    connection.close()


def connect(
    uri: str | Path,
    autocommit: bool = True,
    detect_types: int = sqlite3.PARSE_DECLTYPES,
    timeout: int = 30,
    echo: bool = False,
    adapters: dict[type, AdapterType] = ADAPTERS,
    converters: dict[str, ConverterType] = CONVERTERS,
) -> Database:
    return Database(uri, autocommit, detect_types, timeout, echo, adapters, converters)
