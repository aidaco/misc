from dataclasses import dataclass


@dataclass
class User:
    id: str
    name: str
    password_hash: str
    role_id: str


@dataclass
class Device:
    id: str


@dataclass
class Session:
    id: str
    device_id: str
    user_id: str
    authentication_token: str
    refresh_token: str
