from rich import print
import uuid
import secrets
import functools
from passlib.hash import argon2
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
import fastapi

log = logging.getLogger(__name__)
api = fastapi.FastAPI()

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import create_engine, Session, SQLModel, Field, select

SQL_URL = "sqlite+pysqlite:///:memory:"
EMAIL_REGEX = """(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])"""


engine = create_engine(SQL_URL, echo=True, future=True)
get_session = functools.partial(Session, engine)


def init_db():
    SQLModel.metadata.create_all(engine)


class Account(SQLModel, table=True):
    uid: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    email: str = Field(default=None, regex=EMAIL_REGEX, nullable=False, index=True)
    password_hash: str = Field(default=None, nullable=False)
    created_at: datetime = Field(default_factory=datetime.now)

    def verify(self, password: str) -> bool:
        return argon2.verify(password, self.password_hash)

    @staticmethod
    def create(email, password):
        return Account(email=email, password_hash=argon2.hash(password))

    def __str__(self) -> str:
        return f"<{self.email} {self.uid}>"

    def __repr__(self) -> str:
        return f"Account(uid={self.uid}, email={self.email}, password_hash={self.password_hash})"


class Authentication(SQLModel, table=True):
    account_uid: str = Field(foreign_key="account.uid")
    token: str = Field(default_factory=secrets.token_urlsafe, primary_key=True)
    ttl: timedelta = Field(default_factory=lambda: timedelta(days=30))
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def expired(self):
        return self.created_at + self.ttl < datetime.now()

    def __str__(self):
        return self.token

    def __repr__(self) -> str:
        return f"Authentication({self.token}, created_at={self.created_at}, ttl={self.ttl})"


@api.post("/create", status_code=201)
async def handle_create_request(
    email: str = fastapi.Body(...), password: str = fastapi.Body(...)
):
    with get_session() as session:
        account = Account.create(email, password)
        session.add(account)
        session.commit()
        session.refresh(account)


@api.post("/login")
async def handle_login_request(
    response: fastapi.Response,
    email: str = fastapi.Body(...),
    password: str = fastapi.Body(...),
    ttl: timedelta = fastapi.Body(timedelta(days=30)),
):
    with get_session() as session:
        account = session.exec(select(Account).where(Account.email == email)).first()
        if not account or not account.verify(password):
            raise fastapi.HTTPException(status_code=401, detail="Invalid credentials.")
        auth = Authentication(account_uid=account.uid, ttl=ttl)
        response.set_cookie(key="account-authentication", value=auth.token)
        return auth


@api.post("/resetpassword")
async def handle_reset_password(email: str = fastapi.Body(...)):
    ...
