import appbase
import pydantic
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def test_users():
    def hashpw_unsafe(pw: str) -> str:
        return hashlib.md5(pw.encode()).hexdigest()

    def verifypw_unsafe(pw: str, hash: str) -> bool:
        return hashpw_unsafe(pw) == hash

    class MkUser(pydantic.BaseModel):
        email: str
        password: str = pydantic.Field(min_length=8)
        created: datetime = pydantic.Field(default_factory=utcnow)

        @pydantic.computed_field
        @property
        def password_hash(self) -> str:
            return hashpw_unsafe(self.password)

    @dataclass
    class User:
        id: appbase.database.INTPK
        email: str
        password_hash: str
        created: datetime

        def verifypw(self, pw: str) -> bool:
            return verifypw_unsafe(self.password_hash, pw)

    t = appbase.database.Table(User)
    with (
        appbase.database.lifespan(":memory:") as connection,
        t.cursor(connection) as cursor,
    ):
        cursor.execute(t.create().if_not_exists())
        mkusers = [
            MkUser.model_validate(data)
            for data in [
                {"email": "test1@example.com", "password": "password1"},
                {"email": "test2@example.com", "password": "password2"},
                {"email": "test3@example.com", "password": "password3"},
            ]
        ]

        stmt = t.insert()

        for mkuser in mkusers:
            stmt.values(mkuser)

        cursor.execute(stmt)
        assert (
            cursor.execute(t.count())
            == len(mkusers)
            == len(cursor.execute(t.select()).all())
        )
