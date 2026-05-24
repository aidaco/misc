"""A lightweight user system built on appbase.database and appbase.security.

`User` is a plain dataclass row; `Users` is a repository bound to a `Database`
that handles registration, password authentication (argon2, with transparent
rehashing), and optional JWT issuance/verification:

    db = appbase.database.connect("app.db")
    users = appbase.users.Users(db, token_secret="...")
    users.create_table()
    alice = users.add("alice", "s3cret", email="alice@example.com")
    users.login("alice", "s3cret")
    token = users.issue_token(alice, timedelta(hours=1))
    assert users.authenticate_token(token).id == alice.id
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

from appbase import security
from appbase.database import INTPK, Database, ModelCursor

UNIQUE = Annotated[str, "UNIQUE"]


@dataclass
class User:
    id: INTPK
    name: UNIQUE
    password_hash: str
    created_at: datetime
    updated_at: datetime | None = None
    email: str | None = None


@dataclass
class Users:
    """Repository of `User` rows in a given `Database`."""

    db: Database
    token_secret: str | None = None

    def table(self) -> ModelCursor[User]:
        return self.db.table(User)

    def create_table(self) -> None:
        self.table().create(if_not_exists=True).execute()

    # --- registration & lookup ---

    def add(self, name: str, password: str, email: str | None = None) -> User:
        now = datetime.now(UTC)
        user = (
            self.table()
            .insert(returning=["*"])
            .values(
                name=name,
                password_hash=security.hash_password(password),
                created_at=now,
                updated_at=None,
                email=email,
            )
            .execute()
            .one()
        )
        if user is None:
            raise RuntimeError("Insert did not return the created user.")
        return user

    def get(self, name: str) -> User | None:
        return self.table().select().where(name=name).execute().one()

    def get_by_id(self, id: int) -> User | None:
        return self.table().select().where(id=id).execute().one()

    def all(self) -> list[User]:
        return self.table().select().execute().all()

    def count(self) -> int:
        return self.table().count().get()

    def delete(self, user: User) -> None:
        self.table().delete().where(id=user.id).execute()

    # --- authentication ---

    def login(self, name: str, password: str) -> User:
        user = self.get(name)
        if user is None or not security.verify_password(password, user.password_hash):
            raise ValueError("Login failed.")
        if security.needs_rehash(user.password_hash):
            user = self.set_password(user, password)
        return user

    def set_password(self, user: User, password: str) -> User:
        updated = (
            self.table()
            .update(returning=["*"])
            .set(
                password_hash=security.hash_password(password),
                updated_at=datetime.now(UTC),
            )
            .where(id=user.id)
            .execute()
            .one()
        )
        if updated is None:
            raise ValueError("User not found.")
        return updated

    # --- tokens (optional; require a secret) ---

    def issue_token(self, user: User, dur: timedelta, secret: str | None = None) -> str:
        return security.create_token({"sub": user.name}, dur, self._secret(secret))

    def authenticate_token(self, token: str, secret: str | None = None) -> User:
        payload = security.verify_token(token, self._secret(secret))
        user = self.get(payload["sub"])
        if user is None:
            raise ValueError("Invalid token")
        return user

    def _secret(self, secret: str | None) -> str:
        resolved = secret or self.token_secret
        if resolved is None:
            raise ValueError("No token secret configured.")
        return resolved
