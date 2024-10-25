from datetime import timedelta, datetime, timezone

import argon2
import jwt

_hasher = argon2.PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password_hash, password)


def create_token(data: dict, dur: timedelta, secret: str) -> str:
    return jwt.encode(
        data | {"exp": datetime.now(timezone.utc) + dur},
        secret,
        algorithm="HS256",
    )


def verify_token(token: str, secret: str) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        payload.pop("exp")
        return payload
    except jwt.DecodeError:
        raise ValueError("Invalid token")
