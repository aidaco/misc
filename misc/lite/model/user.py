from typing import Any
from datetime import datetime
from textwrap import dedent
from dataclasses import dataclass


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
