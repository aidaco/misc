import contextlib
from types import UnionType
import typing
import sqlite3
import types
from dataclasses import Field, dataclass, fields
from datetime import datetime, timedelta, timezone
from typing import (
    Annotated,
    Callable,
    ClassVar,
    Literal,
    Protocol,
    Self,
    Iterable,
    Iterator,
    Any,
    Sequence,
    TypeAlias,
)
from pathlib import Path
from textwrap import dedent

import timedelta_isoformat
from pydantic import TypeAdapter


JSONB: TypeAlias = Annotated[bytes, "jsonb"]
INTPK: TypeAlias = Annotated[int, "PRIMARY KEY"]


class DataclassType(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


class ModelType(Protocol):
    @classmethod
    def parse(cls, object: Any) -> Self: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def fields(cls) -> Iterator[tuple[str, type]]: ...


type ConflictResolutionType = Literal["ABORT", "ROLLBACK", "FAIL", "IGNORE", "REPLACE"]


class TableStatementsType(Protocol):
    def table_name(self) -> str: ...
    def column_info(self) -> Iterator[tuple[str, type]]: ...
    def column_defs(self, type_map: dict[type, str]) -> Iterator[str]: ...
    def column_def(self, name: str, cls: type, type_map: dict[type, str]) -> str: ...
    def create_table(self, strict: bool = False) -> str: ...
    def insert(self, conflict: ConflictResolutionType = "ABORT") -> str: ...
    def select(self, predicate: str = "") -> str: ...
    def update(self, filter: str, fields: dict) -> str: ...
    def delete(self, predicate: str) -> str: ...
    def count(self) -> str: ...


class DatabaseType[UriType, ConnectionType, CursorType](Protocol):
    connection: ConnectionType

    @classmethod
    def connect(cls, uri: UriType) -> Self: ...
    @contextlib.contextmanager
    def transact(self) -> Iterator[CursorType]: ...
    def execute(self, sql: str, params: Sequence | dict) -> CursorType: ...
    def table[M: ModelType](
        self, model: type[M], statements: TableStatementsType
    ) -> "Table[M, Self]": ...


type AdapterType[T] = Callable[[T], bytes]
type ConverterType[T] = Callable[[bytes], T]
type TypeAdapterMappingType[M] = dict[type[M], TypeAdapter[M]]

TYPEADAPTER_CACHE: TypeAdapterMappingType = {}


class DataclassMeta(type):
    def __new__(cls, name, bases, dct):
        inst = super().__new__(cls, name, bases, dct)
        return dataclass(inst)  # type: ignore


def typeadapter[M](cls: type[M]) -> TypeAdapter[M]:
    try:
        adapter = TYPEADAPTER_CACHE[cls]
    except KeyError:
        adapter = TYPEADAPTER_CACHE[cls] = TypeAdapter(cls)
    return adapter


class DataclassModel(metaclass=DataclassMeta):
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]

    @classmethod
    def parse(cls, object: Any) -> Self:
        if isinstance(object, tuple | list):
            object = {k[0]: v for k, v in zip(cls.fields(), object)}
        return typeadapter(cls).validate_python(object)

    def to_dict(self) -> dict:
        cls = type(self)
        return typeadapter(cls).dump_python(self, mode="json")

    @classmethod
    def fields(cls) -> Iterator[tuple[str, type]]:
        for field in fields(cls):
            yield (field.name, field.type)


class DataclassStatements[M: ModelType](TableStatementsType):
    def __init__(self, model: type[M]) -> None:
        self.model: type[M] = model

    def table_name(self) -> str:
        return self.model.__name__.casefold()

    def column_info(self) -> Iterator[tuple[str, type]]:
        yield from self.model.fields()

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
            origin = typing.get_origin(t)
            if origin is Annotated:
                match typing.get_args(t):
                    case (_type, _def):
                        constraints = _def
                        unpack_type(_type)
                        return
                    case _:
                        raise TypeError(f"Can only accept one str annotation: {t}")
            elif origin is UnionType:
                match typing.get_args(t):
                    case (_type, types.NoneType) | (types.NoneType, _type):
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

    def insert(self, conflict: ConflictResolutionType = "ABORT") -> str:
        table = self.table_name()
        names = [name for name, _ in self.column_info()]
        columns = ", ".join(names)
        placeholders = ", ".join(f":{name}" for name in names)
        return f"INSERT OR {conflict} INTO {table}({columns}) VALUES ({placeholders}) RETURNING *;"

    def update(self, filter: dict, fields: dict) -> str:
        columns = ",".join(f"{name}=:{name}" for name in fields)
        return f"UPDATE {self.table_name()} SET {columns} WHERE {filter} RETURNING *"

    def delete(self, predicate: str = "") -> str:
        return f"DELETE FROM {self.table_name()} {predicate} RETURNING *;"

    def count(self) -> str:
        table = self.table_name()
        return f"SELECT COUNT(*) FROM {table}"

    def select(self, predicate: str = "") -> str:
        table = self.table_name()
        columns = ", ".join(name for name, _ in self.column_info())
        return f"SELECT {columns} FROM {table} {predicate};"


@dataclass
class Sqlite3Database:
    uri: str | Path
    connection: sqlite3.Connection
    ADAPTERS: ClassVar[dict[type, AdapterType]] = {
        datetime: lambda dt: dt.astimezone(timezone.utc).isoformat().encode(),
        Path: Path.__bytes__,
        timedelta: lambda td: timedelta_isoformat.timedelta.isoformat(td).encode(),
    }
    CONVERTERS: ClassVar[dict[str, ConverterType]] = {
        "datetime": lambda b: datetime.fromisoformat(b.decode()).astimezone(),
        "path": lambda b: Path(b.decode()),
        "timedelta": lambda b: timedelta_isoformat.timedelta.fromisoformat(b.decode()),
    }

    @classmethod
    def connect(cls, uri: Path | str, echo: bool = True) -> Self:
        if isinstance(uri, Path):
            uri.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            uri,
            autocommit=True,  # type: ignore
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=30,
        )
        if echo:
            connection.set_trace_callback(print)
        instance = cls(uri=uri, connection=connection)
        instance.initialize()
        return instance

    def initialize(self) -> None:
        for cls, adapter in self.ADAPTERS.items():
            sqlite3.register_adapter(cls, adapter)
        for name, converter in self.CONVERTERS.items():
            sqlite3.register_converter(name, converter)
        self.connection.executescript(
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

    def finalize(self) -> None:
        self.connection.executescript(
            dedent("""\
            VACUUM;
            PRAGMA analysis_limit=400;
            PRAGMA optimize;
        """)
        )

    def close(self) -> None:
        self.finalize()
        self.connection.close()

    def __del__(self):
        self.close()

    @contextlib.contextmanager
    def transact(self) -> Iterator[sqlite3.Cursor]:
        cursor = self.connection.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")
            yield cursor
            cursor.execute("COMMIT")
        except Exception as exc:
            cursor.execute("ROLLBACK")
            raise exc
        finally:
            cursor.close()

    def execute(
        self, sql: str, params: Sequence | dict[str, Any] = {}
    ) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def table[M: ModelType](
        self, model: type[M], statements: TableStatementsType | None = None
    ) -> "Table[M, Self]":
        return Table.attach(self, model, statements)

    tx = transact
    ex = execute

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc, exc_type, tb) -> None:
        self.close()


@dataclass
class Cursor[M: ModelType]:
    model: type[M]
    cursor: sqlite3.Cursor

    def execute(self, sql: str, params: dict | Sequence | M = {}) -> Self:
        if not isinstance(params, dict | list | tuple):
            params = params.to_dict()  # type: ignore
        self.cursor.execute(sql, params)
        return self

    @property
    def raw(self) -> sqlite3.Cursor:
        return self.cursor

    def one(self) -> M | None:
        row = self.cursor.fetchone()
        return self.model.parse(row) if row is not None else row

    def all(self) -> list[M]:
        return [self.model.parse(row) for row in self.cursor.fetchall()]

    def __iter__(self) -> Iterator[M]:
        yield from (self.model.parse(row) for row in self.cursor)


class Table[M: ModelType, D: DatabaseType](metaclass=DataclassMeta):
    database: D
    model: type[M]
    statements: TableStatementsType
    MODEL: ClassVar[type[ModelType]]
    STATEMENTS: ClassVar[TableStatementsType]

    @classmethod
    def connect(
        cls,
        uri: str,
        model: type[M] | None = None,
        statements: TableStatementsType | None = None,
        echo: bool = True,
        **extra: Any,
    ) -> Self:
        return cls.attach(
            Sqlite3Database.connect(uri, echo), model, statements, **extra
        )

    @classmethod
    def attach(
        cls,
        database: D,
        model: type[M] | None = None,
        statements: TableStatementsType | None = None,
        **extra: Any,
    ) -> Self:
        kwargs: dict[str, Any] = dict(database=database)
        model = model or getattr(cls, "MODEL", None)
        if model is None:
            raise Exception(
                "Must supply model type to __init__ or as classvar on subclass."
            )
        kwargs["model"] = model
        stmts: TableStatementsType = (
            statements or getattr(cls, "statements", None) or DataclassStatements(model)
        )
        kwargs["statements"] = stmts
        inst = cls(**kwargs, **extra)
        inst.initialize()
        return inst

    def cursor(self) -> Cursor[M]:
        return Cursor(self.model, self.database.connection.cursor())

    @contextlib.contextmanager
    def transact(self) -> Iterator[Cursor[M]]:
        with self.database.transact() as cursor:
            yield Cursor(self.model, cursor)

    def execute(self, sql: str, params: dict | Sequence | M = {}) -> Cursor[M]:
        return self.cursor().execute(sql, params)

    def initialize(self) -> None:
        with self.database.transact() as cursor:
            cursor.execute(self.statements.create_table())

    def insert(
        self, param: dict | Sequence | M | None = None, **fields: Any
    ) -> M | None:
        if param is None and not fields:
            raise ValueError("Must pass param object or field kwargs.")
        with self.transact() as cursor:
            return cursor.execute(self.statements.insert(), param or fields).one()

    def insert_from(self, stream: Iterable[M]) -> Iterator[M]:
        for inst in stream:
            if inst := self.insert(inst):
                yield inst

    def get(self, id: int, primary_key_column: str = "rowid") -> M:
        row = self.select(f"where {primary_key_column}=:id", {"id": id}).one()
        if row is None:
            raise ValueError(f"Primary Key {id} not found.")
        return row

    def rm(self, id: int, primary_key_column: str = "rowid") -> M:
        predicate = f"WHERE {primary_key_column}=:id"
        with self.transact() as cursor:
            row = cursor.execute(self.statements.delete(predicate), {"id": id}).one()
        if row is None:
            raise ValueError(f"Primary Key {id} not found.")
        return row

    def update(self, id: int, fields: dict, primary_key_column: str = "rowid") -> M:
        filter = f"{primary_key_column}=:id"
        with self.transact() as cursor:
            row = cursor.execute(
                self.statements.update(filter, fields), {"id": id} | fields
            ).one()
            if row is None:
                raise ValueError("Primary key {id} not found.")
            return row

    def delete(self, predicate: str = "", params: dict[str, Any] = {}) -> Cursor[M]:
        with self.transact() as cursor:
            return cursor.execute(self.statements.delete(predicate), params)

    def count(self) -> int:
        return self.database.connection.execute(self.statements.count()).fetchone()[0]

    def select(self, predicate: str = "", params: dict = {}) -> Cursor[M]:
        return self.execute(self.statements.select(predicate), params)

    def __iter__(self) -> Iterator[M]:
        cursor = self.database.connection.execute(self.statements.select())
        yield from Cursor(self.model, cursor)


Database: TypeAlias = Sqlite3Database
Model: TypeAlias = DataclassModel
