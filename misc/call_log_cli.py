from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Self
from pathlib import Path
import sqlite3

import appbase


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


confconf = appbase.config.ConfigConfig.load(name="call_log")


@confconf.root
class rootconfig:
    datadir: Path = confconf.source.datadir


@confconf.section("auth")
class authconfig:
    jwt_secret: str = "secret"
    jwt_duration: timedelta = timedelta(days=1)


@confconf.section("db")
class config:
    uri: str | Path = rootconfig().datadir / "call_log.sqlite3"


@dataclass
class UserNew:
    name: str
    password: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None

    @property
    def password_hash(self) -> str:
        return appbase.security.hash_password(self.password)


@dataclass
class UserRecord:
    id: int
    name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime | None


class UserStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def create_table(self) -> None:
        self._create_table(self.connection.cursor())

    def create(self, user: UserNew) -> UserRecord:
        return self._insert(self.connection.cursor(), user)

    @staticmethod
    def _create_table(cursor: sqlite3.Cursor) -> None:
        cursor.executescript(
            """
                CREATE TABLE IF NOT EXISTS user(
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME,
                );
            """
        )

    @staticmethod
    def _insert(cursor: sqlite3.Cursor, user: UserNew) -> UserRecord:
        row = cursor.execute(
            """
                INSERT INTO user(name, password_hash, created_at, updated_at)
                VALUES (?,?,?,?)
                RETURNING id, name, password_hash, created_at, updated_at
            """,
            (user.name, user.password_hash, user.created_at, user.updated_at),
        ).fetchone()
        return UserRecord(*row)

    @staticmethod
    def _select_by_name(cursor: sqlite3.Cursor, name: str) -> UserRecord:
        row = cursor.execute(
            """
                SELECT id, name, password_hash, created_at, updated_at
                FROM user
                WHERE name = ?
            """,
            (name,),
        ).fetchone()
        return UserRecord(*row)

    def login(self, name: str, password: str) -> UserRecord:
        user = self._select_by_name(self.connection.cursor(), name)
        if not appbase.security.verify_password(password, user.password_hash):
            raise ValueError("Login failed.")
        return user


@dataclass
class CallNew:
    number: str
    caller: str
    received_by_id: int
    notes: str
    received_at: datetime = field(default_factory=utcnow)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None


@dataclass
class CallRecord:
    id: int
    received_at: datetime
    received_by_id: int
    number: str
    caller: str
    notes: str
    created_at: datetime
    updated_at: datetime | None


class CallStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _create_table(self, cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
                
            """
        )

    @classmethod
    def create(
        cls,
        received_at: datetime,
        received_by: User,
        number: str,
        caller: str,
        notes: str,
    ) -> Self:
        return (
            cls.table()
            .insert()
            .values(
                received_at=received_at,
                received_by_id=received_by.id,
                number=number,
                caller=caller,
                notes=notes,
                created_at=utcnow(),
            )
            .execute()
            .one()
        )

    @classmethod
    def get(cls, id: int) -> Self:
        return cls.table().select().where(id=id).execute().one()


@dataclass
class Task:
    id: INTPK
    user_id: int
    call_id: int | None
    name: str
    notes: str
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def table(cls) -> Table[Self]:
        return Table(cls)

    @classmethod
    def create(
        cls,
        user: User,
        call: Call | None,
        name: str,
        notes: str,
    ) -> Self:
        return (
            cls.table()
            .insert()
            .values(
                user_id=user.id,
                call_id=None if call is None else call.id,
                name=name,
                notes=notes,
                created_at=utcnow(),
            )
            .returning("*")
            .execute()
            .one()
        )


if __name__ == "__main__":
    ...
