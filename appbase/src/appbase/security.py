from datetime import UTC, datetime, timedelta

import argon2
import jwt
from argon2.exceptions import VerifyMismatchError

_hasher = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def create_token(data: dict, dur: timedelta, secret: str) -> str:
    return jwt.encode(
        data | {"exp": datetime.now(UTC) + dur},
        secret,
        algorithm="HS256",
    )


def verify_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token") from None
    payload.pop("exp", None)
    return payload
