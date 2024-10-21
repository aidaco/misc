from datetime import datetime, timezone
from typing import Annotated, Iterator
import smtplib
import email.message

from appbase.database import Model, Table, Database, INTPK
import appbase.security as security


class User(Model):
    id: INTPK
    name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime | None


class UserStore(Table[User, Database]):
    MODEL = User

    def insert(  # type: ignore
        self,
        name: str,
        password: str,
    ) -> User | None:
        return super().insert(
            (
                name,
                security.hash_password(password),
                datetime.now(timezone.utc),
            )
        )

    def login(self, name: str, password: str) -> User:
        row = self.select("WHERE name=:name", {"name": name}).one()
        if row is None or not security.verify_password(password, row.password_hash):
            raise ValueError("Login failed.")
        return row


class Email(Model):
    id: INTPK
    user_id: Annotated[int, "references user(id) on update cascade on delete cascade"]
    address: Annotated[str, "unique"]
    priority: int
    created: datetime
    updated: datetime | None

    def send_message(
        self,
        subject: str,
        body: str,
        smtp: smtplib.SMTP,
    ):
        msg = email.message.EmailMessage()
        msg["From"] = smtp.user
        msg["To"] = self.address
        msg["Subject"] = subject
        msg.set_content(body)
        smtp.send_message(msg)


class EmailStore(Table):
    def for_user(self, user: User) -> Iterator[User]:
        yield from self.execute("where user_id=:id", {"id": user.id})

    def insert(  # type: ignore
        self, user: User, address: str, priority: int = 0
    ) -> User | None:
        return super().insert(
            {
                "user_id": user.id,
                "address": address,
                "priority": priority,
                "created": datetime.now(timezone.utc),
                "updated": None,
            }
        )
