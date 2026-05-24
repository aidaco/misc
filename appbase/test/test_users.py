import sqlite3
from datetime import timedelta

import pytest

import appbase
from appbase.users import Users


@pytest.fixture
def users():
    with appbase.database.connect(":memory:") as db:
        store = Users(db, token_secret="super-secret-key-of-sufficient-length!!")
        store.create_table()
        yield store


def test_add_and_get(users):
    alice = users.add("alice", "s3cret", email="alice@example.com")
    assert alice.id is not None
    assert alice.name == "alice"
    assert alice.email == "alice@example.com"
    assert alice.password_hash != "s3cret"  # stored hashed, not plaintext

    fetched = users.get("alice")
    assert fetched is not None and fetched.id == alice.id
    assert users.get_by_id(alice.id).id == alice.id
    assert users.get("nobody") is None
    assert users.count() == 1


def test_login_success_and_failure(users):
    users.add("bob", "hunter2")
    assert users.login("bob", "hunter2").name == "bob"
    with pytest.raises(ValueError):  # wrong password -> verify_password returns False
        users.login("bob", "wrong")
    with pytest.raises(ValueError):  # unknown user
        users.login("ghost", "whatever")


def test_set_password(users):
    bob = users.add("bob", "old-pw")
    users.set_password(bob, "new-pw")
    assert users.login("bob", "new-pw").name == "bob"
    with pytest.raises(ValueError):
        users.login("bob", "old-pw")


def test_unique_name(users):
    users.add("carol", "pw1")
    with pytest.raises(sqlite3.IntegrityError):
        users.add("carol", "pw2")


def test_tokens(users):
    alice = users.add("alice", "s3cret")
    token = users.issue_token(alice, timedelta(hours=1))
    assert users.authenticate_token(token).id == alice.id

    expired = users.issue_token(alice, timedelta(seconds=-1))
    with pytest.raises(ValueError):  # expired -> verify_token raises ValueError
        users.authenticate_token(expired)


def test_token_requires_secret():
    with appbase.database.connect(":memory:") as db:
        store = Users(db)  # no token_secret configured
        store.create_table()
        alice = store.add("alice", "pw")
        with pytest.raises(ValueError):
            store.issue_token(alice, timedelta(hours=1))


def test_delete(users):
    bob = users.add("bob", "pw")
    users.delete(bob)
    assert users.get("bob") is None
    assert users.count() == 0
