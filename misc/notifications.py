import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import TypedDict, Self
from pydantic import TypeAdapter, Json
import json


class SubscriptionKeys(TypedDict):
    auth: str
    p256dh: str


class SubscriptionInfo(TypedDict):
    endpoint: str
    keys: SubscriptionKeys


@dataclass
class Subscription:
    id: int
    user_id: int
    info: Json[SubscriptionInfo]
    created_at: datetime
    expired_at: datetime | None

    @staticmethod
    def create_table(connection: sqlite3.Connection) -> None:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS subscription(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                info JSON,
                created_at TEXT NOT NULL,
                expired_at TEXT
            )
        """)

    @classmethod
    def add(
        cls,
        connection: sqlite3.Connection,
        user_id: int,
        info: SubscriptionInfo,
    ) -> Self:
        with connection:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO subscription(user_id, info, created_at) VALUES (?, ?, ?)",
                (user_id, json.dumps(info), datetime.now(tz=timezone.utc)),
            )
            return cursor.execute(
                "SELECT * FROM subscription WHERE id=?", (cursor.lastrowid,)
            ).fetchone()

    @classmethod
    def parse(cls, fields: dict) -> Self:
        return cls(
            id=int(fields["id"]),
            user_id=int(fields["user_id"]),
            info=json.loads(fields["info"]),
            created_at=datetime.fromisoformat(fields["created_at"]),
            expired_at=None
            if fields["expired_at"] is None
            else datetime.fromisoformat(fields["expired_at"]),
        )

    @classmethod
    def parse_pydantic(cls, fields: dict) -> Self:
        adapter = TypeAdapter(Subscription)
        return adapter.validate_python(fields)


def std():
    cx = sqlite3.connect(":memory:")
    cx.row_factory = sqlite3.Row
    Subscription.create_table(cx)
    s = Subscription.add(cx, 1, {"endpoint": "", "keys": {"auth": "", "p256dh": ""}})
    Subscription.parse(s)


def pyd():
    cx = sqlite3.connect(":memory:")

    def fact(cur, row):
        return {k: v for k, v in zip((c[0] for c in cur.description), row)}

    cx.row_factory = fact
    Subscription.create_table(cx)
    s = Subscription.add(cx, 1, {"endpoint": "", "keys": {"auth": "", "p256dh": ""}})
    Subscription.parse_pydantic(s)
