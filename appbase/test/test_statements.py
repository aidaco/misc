from dataclasses import dataclass

import pytest

import appbase
from appbase.database import INTPK


@dataclass
class Row:
    id: INTPK
    v: str


@pytest.fixture
def db():
    with appbase.database.connect(":memory:") as conn:
        yield conn


def test_update_conflict_emits_or_replace(db):
    # Update.conflict() used to set the wrong attribute and emit nothing.
    stmt = db.table(Row).update().conflict("REPLACE").set(v="x").where(id=1)
    assert "UPDATE OR REPLACE" in str(stmt)


def test_select_where_kwargs_builds_clause(db):
    stmt = db.table(Row).select().where(v="x")
    assert "WHERE v=:v" in str(stmt)


def test_select_where_string_passthrough(db):
    stmt = db.table(Row).select().where("v IS NOT NULL")
    assert "WHERE v IS NOT NULL" in str(stmt)


def test_insert_values_shape_mismatch_raises(db):
    # Batched rows must share a shape; mismatches now raise ValueError (not assert).
    with pytest.raises(ValueError):
        db.table(Row).insert().values(id=1, v="a").values(v="b")


def test_insert_executemany_roundtrip(db):
    db.table(Row).create(if_not_exists=True).execute()
    db.table(Row).insert().values(id=1, v="a").values(id=2, v="b").execute()
    assert db.table(Row).count().get() == 2
