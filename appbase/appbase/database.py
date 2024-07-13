import sqlite3
from dataclasses import dataclass, field
from typing import (
    Self,
    Protocol,
    Iterator,
)
from datetime import datetime
from contextlib import contextmanager
import re

import pydantic
from pydantic import TypeAdapter

try:
    import pysqlite3 as sqlite3  # type: ignore
except Exception:
    pass

# from wwwmin.config import config as main_config


# @main_config.section("database")
# class config:
#     uri: str = str(
#         (Path(appdirs.user_data_dir("wwwmin")) / "database.sqlite3").resolve()
#     )


class AdaptableType[Model](Protocol):
    @classmethod
    def parse(cls, row: sqlite3.Row) -> Model: ...


TYPEADAPTER_CACHE: dict[type, TypeAdapter] = dict()


def get_typeadapter[T](type: type[T]) -> TypeAdapter[T]:
    try:
        return TYPEADAPTER_CACHE[type]
    except KeyError:
        TYPEADAPTER_CACHE[type] = pydantic.TypeAdapter(type)
    return TYPEADAPTER_CACHE[type]


@dataclass
class Cursor[Model]:
    cursor: sqlite3.Cursor
    model: type[AdaptableType[Model]]

    def one(self) -> Model:
        return self.model.parse(self.cursor.fetchone())

    def list(self) -> list[Model]:
        return [self.model.parse(row) for row in self.cursor.fetchall()]

    def __iter__(self) -> Iterator[Model]:
        return (self.model.parse(row) for row in self.cursor)


class TableMeta(type):
    NAME: str
    CREATE: str
    INSERT: str
    SELECT: str = "select * from {name}"
    GET: str = "where id=:id"
    UPDATE: str = "update {name} {predicate} returning *"

    def __new__(cls, name, bases, dct, init=True):
        inst = super().__new__(cls, name, bases, dct)
        if init:
            inst = dataclass(inst)  # type: ignore
        return inst

    def do[T](cls, o: T) -> T:
        return o


class Table(metaclass=TableMeta, init=False):
    @classmethod
    def parse(cls, row: sqlite3.Row) -> Self:
        return get_typeadapter(cls).validate_python(dict(row))

    @classmethod
    def bind[T: "Table"](cls: type[T], database: "Database") -> "BoundTable[T]":
        return BoundTable(
            name=getattr(cls, "NAME", database.default_name(cls)),
            table=cls,
            database=database,
        )


# class TableInfo(Protocol):
#     NAME: str
#     CREATE: str
#     INSERT: str
#     SELECT: str
#     UPDATE: str
#     GET: str


@dataclass
class BoundTable[T: Table]:
    name: str
    table: type[T]
    database: "Database"

    @property
    def model(self) -> type[T]:
        return table

    def create(self) -> None:
        self.database.query(self.table.CREATE)

    def query(self, sql: str, params: dict | None = None, **kwparams) -> Cursor[T]:
        return Cursor(
            cursor=self.database.query(sql, params if params is not None else kwparams),
            model=self.table,
        )

    def insert(self, params: dict | None = None, **kwparams) -> T:
        return self.query(
            self.table.INSERT, params if params is not None else kwparams
        ).one()

    def select(
        self, predicate: str = "", params: dict | None = None, **kwparams
    ) -> Cursor[T]:
        return self.query(
            f"{self.table.SELECT.format(name=self.name)} {predicate}",
            params if params is not None else kwparams,
        )

    def update(
        self, predicate: str, params: dict | None = None, **kwparams
    ) -> Cursor[T]:
        return self.query(
            self.table.UPDATE.format(name=self.name, predicate=predicate),
            params if params is not None else kwparams,
        )

    def get(self, params: dict | None = None, **kwparams) -> T | None:
        return self.select(
            self.table.GET.format(name=self.name),
            params if params is not None else kwparams,
        ).one()


@dataclass(unsafe_hash=True)
class Database:
    uri: str = field(hash=True)
    connection: sqlite3.Connection = field(init=False, hash=False)

    @property
    def tables(self):
        cls = type(self)
        return [
            getattr(self, key)
            for key, value in vars(cls).items()
            if isinstance(value, TableMeta)
        ]

    def connect(self) -> None:
        self.connection: sqlite3.Connection = sqlite3.connect(
            self.uri, isolation_level=None
        )
        self.configure_sqlite()
        self.create_tables()

    def configure_sqlite(self):
        sqlite3.register_adapter(datetime, datetime.isoformat)
        sqlite3.register_converter(
            "datetime", lambda b: datetime.fromisoformat(b.decode("utf-8"))
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            pragma journal_mode = WAL;
            pragma synchronous = normal;
            pragma temp_store = memory;
            pragma mmap_size = 30000000000;
            pragma foreign_keys = on;
            pragma auto_vacuum = incremental;
            pragma foreign_keys = on;
        """)

    @classmethod
    def default_name(
        cls, table: TableMeta, replace_regex=re.compile("(?<!^)(?=[A-Z])")
    ) -> str:
        return replace_regex.sub("_", table.__name__).lower()

    def bind[T: Table](self, table: type[T]) -> BoundTable[T]:
        return table.bind(self)  # type: ignore broken by functools.cache

    def create_tables(self):
        for table in self.tables:
            table.create()

    def query(self, sql: str, params: dict | None = None, **kwparams) -> sqlite3.Cursor:
        return self.connection.execute(sql, params or kwparams)

    @contextmanager
    def transact(self):
        with self.connection:
            cursor = self.connection.cursor()
            cursor.execute("BEGIN")
            yield cursor

    def __enter__(self):
        try:
            return self.connection
        except AttributeError:
            self.connect()
        return self.connection

    def __exit__(self, *_) -> None:
        self.connection.close()


db = Database(":memory:")


@db.bind
class user(Table):
    CREATE = "create table user(name text)"
    INSERT = "insert into user values (:name) returning *"
    name: str
