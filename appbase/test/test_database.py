import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import patch

import pydantic
import pytest

import appbase


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def test_database_context_manager():
    db = appbase.database.connect(":memory:")
    with (
        patch.object(db, "connect") as connect_mock,
        patch.object(db, "close") as close_mock,
        db,
    ):
        pass
    connect_mock.assert_called_once()
    close_mock.assert_called_once()


@pytest.fixture
def memdb():
    with appbase.database.connect(":memory:") as db:
        yield db


def test_users(memdb):
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

    with memdb.table(User) as users:
        users.create().if_not_exists().execute()
        mkusers = [
            MkUser.model_validate(data)
            for data in [
                {"email": "test1@example.com", "password": "password1"},
                {"email": "test2@example.com", "password": "password2"},
                {"email": "test3@example.com", "password": "password3"},
            ]
        ]

        stmt = users.insert()

        for mkuser in mkusers:
            stmt.values(mkuser)

        stmt.execute()
        assert (
            users.count().get() == len(mkusers) == len(users.select().execute().all())
        )


def test_close_does_not_raise_under_concurrent_writer(tmp_path):
    dbpath = tmp_path / "appbase.db"
    a = appbase.database.connect(dbpath)
    conn_a = a.connect()
    conn_a.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")

    # timeout=0 -> fail fast on lock contention instead of waiting busy_timeout.
    b = appbase.database.connect(dbpath, timeout=0)
    b.connect()

    # A holds the WAL write lock. The old close ran VACUUM, which needs a
    # database-wide exclusive lock and raised OperationalError('database is
    # locked') straight out of close(). The new close runs incremental_vacuum and
    # swallows the busy error (best-effort), so it still closes cleanly and the
    # reclamation is deferred to whichever connection closes while the DB is idle.
    conn_a.execute("BEGIN IMMEDIATE")
    conn_a.execute("INSERT INTO t (v) VALUES ('x')")

    b.close()  # must not raise

    conn_a.execute("COMMIT")
    a.close()


def test_vacuum_method(tmp_path):
    dbpath = tmp_path / "appbase.db"
    with appbase.database.connect(dbpath) as db:
        cur = db.cursor()
        cur.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        cur.execute("INSERT INTO t (v) VALUES ('x')")
        db.vacuum()  # explicit full compaction, single connection — must not raise
        assert db.cursor().execute("SELECT count(*) FROM t").fetchone()[0] == 1
