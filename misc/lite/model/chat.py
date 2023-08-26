from dataclasses import dataclass
from datetime import datetime


@dataclass
class Chat:
    id: str


@dataclass
class Participant:
    id: str
    user_id: str
    chat_id: str


@dataclass
class Message:
    id: str
    time: datetime
    user_id: str
    chat_id: str
    content: str
