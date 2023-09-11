import typing
from datetime import datetime
from textwrap import dedent
from dataclasses import dataclass

def get_column_info(field):
    name = field.name
    decltype = field.type if isinstance(field.type, str) else field.type.__name__
    constraints = field.type.__metadata__ if typing.get_origin(field.type) == typing.Annotated else ()
    return name, decltype, constraints


def make_column_decl(field):
    name, decltype, constraints = get_column_info(field)
    return f'{name} {decltype}' if not constraints else f'{name} {decltype} {" ".join(constraints)}'


def generate_create_query(datacls: type) -> str:
    name = datacls.__name__
    columns = ', '.join(map(make_column_decl, fields(datacls)))
    return f"CREATE TABLE IF NOT EXISTS {name} ({columns});"


def generate_insert_query(datacls: type) -> str:
    name = datacls.__name__
    columns = ', '.join((field for field in fields(datacls)))
    placeholders = ', '.join([':' + x.name for x in fields(datacls)])
    return f"INSERT INTO {name} ({columns}) VALUES ({placeholders});"

def generate_get_query(datacls: type) -> str:
    name = datacls.__name__
    columns = ', '.join((field for field in fields(datacls)))
    return f"SELECT * FROM {name};"


@dataclass
class SQLQuery:
    text: str
    vars: dict


def sql(text: str, params: dict = None) -> SQLQuery:
    return SQLQuery(dedent(text).strip(), params or {})


@dataclass
class Database:
    uri: str
    connection: Any


@dataclass
class User:
    id: str
    name: str
    created_at: datetime

    def ensure_table():
        return sql(
            """
            CREATE TABLE IF NOT EXISTS User (
                id INTEGER PRIMARY KEY,
                name TEXT,
                created_at TEXT,
            );
            """
        )

    @staticmethod
    def create(name: str) -> SQLQuery:
        return sql(
            """
            INSERT INTO User (name)
            VALUES (:name)
            """,
            {"name": name},
        )

    @staticmethod
    def update(id: str, name: str) -> SQLQuery:
        return sql(
            """
            UPDATE User
            SET name = :name
            WHERE id = :id
            """,
            {"id": id, "name": name},
        )


@dataclass
class Device:
    id: str


@dataclass
class Session:
    id: str
    device_id: str
    user_id: str
    authentication_token: str
    refresh_token: str
