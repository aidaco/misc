from dataclasses import dataclass
from typing import Protocol


class ContactMethod(Protocol):
    def send(self, message: str) -> None:
        pass


@dataclass
class WebPush:
    id: str
    device_id: str
    user_id: str
    subscription_info: str

    def send(self, message: str) -> None:
        pass


@dataclass
class PhoneType:
    id: str
    name: str


@dataclass
class Phone:
    id: str
    user_id: str
    number: str
    type_id: str
    preference: int

    def send(self, message: str) -> None:
        pass


@dataclass
class Email:
    id: str
    user_id: str
    address: str
    preference: int

    def send(self, message: str) -> None:
        pass
