import dataclasses
import logging
import typing
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import dateutil.parser
import fastapi
from jose import jwe
from passlib.hash import argon2
from rich import print

log = logging.getLogger(__name__)
api = fastapi.FastAPI()

SECRET_KEY = "z$C&F)J@NcRfUjXn"
EMAIL_REGEX = """^(?:[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*|"(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21\x23-\x5b\x5d-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])*")@(?:(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|\[(?:(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9]))\.){3}(?:(2(5[0-5]|[0-4][0-9])|1[0-9][0-9]|[1-9]?[0-9])|[a-z0-9-]*[a-z0-9]:(?:[\x01-\x08\x0b\x0c\x0e-\x1f\x21-\x5a\x53-\x7f]|\\[\x01-\x09\x0b\x0c\x0e-\x7f])+)\])$"""


SQLITE_PATH = ":memory:"


@dataclass
class JWETokenizer:
    cls: typing.Type
    secret: str = SECRET_KEY
    algorithm: str = "dir"
    encryption: str = "A128GCM"

    def dumps(self, obj) -> str:
        return jwe.encrypt(
            ",".join(f"{k}={v}" for k, v in dataclasses.asdict(obj).items()),
            self.secret,
            algorithm=self.algorithm,
            encryption=self.encryption,
        )

    def loads(self, token: str) -> typing.Any:
        return self.cls(
            **dict(
                pair.split("=") for pair in jwe.decrypt(token, self.secret).split(",")
            )
        )


@dataclass
class User:
    email: str
    password_hash: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def create(cls, email, password) -> "User":
        return cls(email, argon2.hash(password))

    def verify(self, password: str) -> bool:
        return argon2.verify(password, self.password_hash)


@dataclass
class Session:
    userid: str
    created: datetime = field(default_factory=datetime.now)
    ttl: timedelta = field(default_factory=lambda: timedelta(days=30))
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


@api.on_event("startup")
async def startup():
    ...


@api.post("/create", status_code=201)
async def handle_create_request(
    email: str = fastapi.Body(...), password: str = fastapi.Body(...)
):
    ...


@api.post("/login")
async def handle_login_request(
    response: fastapi.Response,
    email: str = fastapi.Body(...),
    password: str = fastapi.Body(...),
    ttl: timedelta = fastapi.Body(timedelta(days=30)),
):
    ...


@api.post("/resetpassword")
async def handle_reset_password(email: str = fastapi.Body(...)):
    ...
