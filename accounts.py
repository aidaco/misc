from rich import print
import uuid
import secrets
import pickle
from functools import cached_property
from passlib.hash import argon2
from datetime import datetime, timedelta
from dataclasses import dataclass, field, InitVar


@dataclass
class Token:
    value: str = field(default_factory=secrets.token_urlsafe)
    created_at: datetime = field(default_factory=datetime.now)
    ttl: timedelta = field(default_factory=lambda: timedelta(hours=24))

    def expired(self):
        return self.created_at + self.ttl < datetime.now()


@dataclass
class Account:
    email: str
    password_hash: str
    uid: str = field(default_factory=lambda: uuid.uuid4().hex)

    def check_password(self, attempt):
        return argon2.verify(attempt, self.password_hash)

    def set_password(self, new):
        self.password_hash = argon2.hash(new)

    def reset_password(self):
        return PasswordReset.request(self)

    @staticmethod
    def create(email, password):
        if email in accounts:
            raise ValueError("Email is already in use.")
        acc = Account(email, argon2.hash(password))
        accounts[acc.uid] = acc
        return acc

    @staticmethod
    def login(email, password):
        try:
            acc = next(filter(lambda a: a.email == email, accounts.values()))
        except StopIteration:
            raise ValueError("Invalid credentials.")

        if not acc.check_password(password):
            raise ValueError("Invalid credentials.")
        return Session(acc)

    @staticmethod
    def get(email):
        return accounts.get(email)


@dataclass
class PasswordReset:
    account: Account
    token: Token = field(default_factory=Token)

    @classmethod
    def request(cls, account):
        req = cls(account)
        pwresets[req.token.value] = req
        send_message(account, f"Confirm your email: {req.token.value}")
        return req

    @classmethod
    def resolve(cls, token, cur, new):
        reset = pwresets.get(token)
        if reset.token.expired():
            raise ValueError("Expired token.")
        elif not reset.account.check_password(cur):
            raise ValueError("Invalid credentials.")

        reset.account.set_password(new)
        del pwresets[token]

    @staticmethod
    def get(token):
        return pwresets.get(token.value)


class SessionData:
    def serialize(self):
        return pickle.dumps(self)

    @staticmethod
    def deserialize(data):
        return pickle.loads(data)


@dataclass
class Session:
    account: Account
    data: str | None = None
    token: Token = field(default_factory=Token)

    @cached_property
    def store(self) -> SessionData:
        return SessionData.deserialize(self.store)

    @staticmethod
    def get(token):
        return sessions.get(token)


def send_message(account: Account, message: str):
    print(f"Sending message to {account.email}: {message}")


accounts: dict[str, Account] = {}
sessions: dict[str, Session] = {}
pwresets: dict[str, PasswordReset] = {}


def main():
    accs = [Account.create(f"testuser{i}@web.com", f"password{i}") for i in range(10)]
    print(f"{accs=}")
    a0 = accs[0]
    pwr = a0.reset_password()
    print(f"{pwr}")
    sess = Account.login("testuser0@web.com", "password0")
    print(f"{sess}")


if __name__ == "__main__":
    main()
