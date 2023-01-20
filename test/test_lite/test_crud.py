import lite
from dataclasses import dataclass, field


@dataclass
class User:
    name: str
    password_hash: str


def test_create():
    db = lite.Database(":memory:", users=User)
    db.users.init()
    db.users.create("John Doe", "hash")
    u1 = db.users.find(db.users.name == "John Doe")
    u2 = db.users.get(u1.id)
    assert u1 == u2
