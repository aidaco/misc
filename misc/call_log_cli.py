from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Annotated, ClassVar, Self
from pathlib import Path
import sqlite3

import appbase
from misc.textual_dictform import modelinput


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
class dbconfig:
    uri: str | Path = rootconfig().datadir / "call_log.sqlite3"


def connect() -> appbase.database.Database:
    return appbase.database.connect(dbconfig().uri)


def expect[T](value: T | None) -> T:
    if value is None:
        raise ValueError("Unexpected None.")
    return value


@dataclass
class LoginParams:
    username: str
    password: str

    def password_hash(self) -> str:
        return appbase.security.hash_password(self.password)

    def as_params(self) -> "UserParams":
        return UserParams(self.username, self.password_hash())


@dataclass
class UserParams:
    name: str
    password_hash: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None


@dataclass
class User:
    id: appbase.database.INTPK
    name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime | None


class UserStore:
    def __init__(self, db: appbase.database.Database) -> None:
        self.db: appbase.database.Database = db

    def create_table(self) -> None:
        self.db.table(User).create().if_not_exists().execute()

    def insert(self, user: UserParams) -> User:
        return expect(
            self.db.table(User).insert().values(user).returning("*").execute().one()
        )

    def select_by_name(self, name: str) -> User:
        return expect(self.db.table(User).select().where(name=name).execute().one())

    def login(self, name: str, password: str) -> User:
        user = self.select_by_name(name)
        if not appbase.security.verify_password(password, user.password_hash):
            raise ValueError("Login failed.")
        return user


@dataclass
class CallNote:
    number: str
    caller: str
    notes: str

    def as_params(self, user: User) -> "CallParams":
        return CallParams(
            number=self.number,
            caller=self.caller,
            received_by_id=user.id,
            notes=self.notes,
        )


@dataclass
class CallParams:
    number: str
    caller: str
    notes: str
    received_by_id: int
    received_at: datetime = field(default_factory=utcnow)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None


@dataclass
class Call:
    id: appbase.database.INTPK
    number: str
    caller: str
    notes: str
    user_id: Annotated[int, "REFERENCES user(id) ON UPDATE CASCADE ON DELETE CASCADE"]
    received_at: datetime
    created_at: datetime
    updated_at: datetime | None


class CallStore:
    def __init__(self, db: appbase.database.Database) -> None:
        self.db: appbase.database.Database = db

    def create_table(self) -> None:
        self.db.table(Call).create().if_not_exists().execute()

    def insert(self, call: CallParams) -> Call:
        return expect(
            self.db.table(Call).insert().values(call).returning("*").execute().one()
        )


@dataclass
class TaskParams:
    name: str
    notes: str
    user_id: int
    call_id: int | None = None
    received_at: datetime = field(default_factory=utcnow)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Task:
    id: appbase.database.INTPK
    user_id: Annotated[int, "REFERENCES user(id) ON UPDATE CASCADE ON DELETE CASCADE"]
    call_id: Annotated[
        int | None, "REFERENCES call(id) ON UPDATE CASCADE ON DELETE CASCADE"
    ]
    name: str
    notes: str
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None


class TaskStore:
    def __init__(self, db: appbase.database.Database) -> None:
        self.db: appbase.database.Database = db

    def create_table(self) -> None:
        self.db.table(Task).create().if_not_exists().execute()

    def insert(self, task: TaskParams) -> Task:
        return expect(
            self.db.table(Task).insert().values(task).returning("*").execute().one()
        )


if __name__ == "__main__":
    ...
