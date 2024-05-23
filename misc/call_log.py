from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import pysqlite3 as sqlite3
from typing import Self, Annotated, ClassVar, Iterator
from urllib.parse import quote
from textwrap import dedent

from fastapi import FastAPI, Form, Depends, Query, Cookie, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
import jwt
import jinja2
import appdirs
import argon2
import uvicorn

hasher = argon2.PasswordHasher()
db_uri = appdirs.user_data_dir("call_log")
jwt_secret = "secret"
jwt_duration = timedelta(days=1)

sqlite3.register_adapter(datetime, datetime.isoformat)
sqlite3.register_converter(
    "datetime", lambda b: datetime.fromisoformat(b.decode("utf-8"))
)


class TableMeta(type):
    CREATE: ClassVar[str]
    NAME: ClassVar[str]
    database: ClassVar["Database"]

    def __new__(cls, name, bases, dct):
        instance = super().__new__(cls, name, bases, dct)
        instance = dataclass(instance)
        if name != "Table":
            Database.add_table(instance)
        return instance

    @classmethod
    def set_database(cls, database: "Database") -> None:
        cls.database = database


@dataclass
class Database:
    uri: str = ":memory:"
    connection: sqlite3.Connection | None = None
    connect_config: str = dedent("""
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = normal;
        PRAGMA temp_store = memory;
        PRAGMA mmap_size = 30000000000;
        PRAGMA foreign_keys = on;
        PRAGMA auto_vacuum = incremental;
    """)
    tables: ClassVar[set[type[TableMeta]]] = set()

    def __post_init__(self) -> None:
        for table in self.tables:
            table.set_database(self)

    def connect(self) -> sqlite3.Connection:
        if self.connection is None:
            connection = sqlite3.connect(self.uri)
            connection.row_factory = sqlite3.Row
            connection.executescript(self.connect_config)
            connection.executescript(
                ";".join(dedent(table.CREATE) for table in self.tables)
            )
            self.connection = connection
        return self.connection

    def query(self, query, *args, **kwargs):
        print(query)
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(dedent(query), *args, **kwargs)
            yield from cursor

    def queryone(self, query, *args, **kwargs):
        print(query)
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(dedent(query), *args, **kwargs)
            return cursor.fetchone()

    def exec(self, *args, **kwargs):
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.executescript(*args, **kwargs)

    @classmethod
    def add_table[T: type[TableMeta]](cls, table_cls: T) -> T:
        cls.tables.add(table_cls)
        return table_cls


class Table(metaclass=TableMeta):
    @classmethod
    def get(cls, id: int) -> Self:
        return cls(
            **cls.database.queryone(f"SELECT * FROM {cls.NAME} WHERE id=?", (id,))
        )

    @classmethod
    def all(cls) -> Iterator[Self]:
        yield from (
            cls(**row) for row in cls.database.query(f"SELECT * FROM {cls.NAME}")
        )

    @classmethod
    def where(cls, *predicates, **values) -> Iterator[Self]:
        predicates = [
            *predicates,
            *(f"{column}=?" for column in values),
        ]
        yield from (
            cls(**row)
            for row in cls.database.query(
                f"SELECT * FROM {cls.NAME} WHERE {" AND ".join(predicates)}",
                tuple(values.values()),
            )
        )


CLOSE_CONFIG = """
PRAGMA vacuum;
PRAGMA incremental_vacuum;
PRAGMA optimize;
"""


class User(Table):
    CREATE: ClassVar[str] = """CREATE TABLE IF NOT EXISTS user(
        id integer primary key autoincrement,
        name text not null unique,
        password_hash text not null,
        created_at datetime not null,
        updated_at datetime
    )"""
    NAME: ClassVar[str] = "user"
    id: int
    name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def create(
        cls,
        name: str,
        password: str,
    ) -> Self:
        return cls(
            **cls.database.queryone(
                "INSERT INTO user(name, password_hash, created_at) VALUES (?,?,?) RETURNING *;",
                (
                    name,
                    hasher.hash(password),
                    datetime.now(timezone.utc),
                ),
            )
        )

    @classmethod
    def login(cls, name: str, password: str) -> Self:
        row = cls.database.queryone("SELECT * FROM user WHERE name=?;", (name,))
        if row is None or not verify_password(password, row["password_hash"]):
            raise ValueError("Login failed.")
        return cls(**row)


class Call(Table):
    CREATE: ClassVar[str] = """CREATE TABLE IF NOT EXISTS call(
        id integer primary key autoincrement,
        received_at datetime not null,
        received_by_id integer not null,
        number text,
        caller text,
        notes text,
        created_at datetime not null,
        updated_at datetime
    )"""
    id: int
    received_at: datetime
    received_by_id: int
    number: str
    caller: str
    notes: str
    created_at: datetime
    updated_at: datetime | None

    @classmethod
    def create(
        cls,
        received_at: datetime,
        received_by: User,
        number: str,
        caller: str,
        notes: str,
    ) -> Self:
        return cls(
            **cls.database.queryone(
                """
                INSERT INTO call(
                    received_at,
                    received_by_id,
                    number,
                    caller,
                    notes,
                    created_at
                )
                VALUES (?,?,?,?,?,?)
                RETURNING *""",
                (
                    received_at,
                    received_by.id,
                    number,
                    caller,
                    notes,
                    datetime.now(timezone.utc),
                ),
            )
        )


class Task(Table):
    CREATE: ClassVar[str] = """CREATE TABLE IF NOT EXISTS task(
        id integer primary key autoincrement,
        user_id integer not null,
        call_id integer,
        name text not null,
        notes text,
        created_at datetime not null,
        updated_at datetime,
        completed_at datetime
    )"""
    id: int
    user_id: int
    call_id: int | None
    name: str
    notes: str
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def create(
        cls,
        user: User,
        call: Call | None,
        name: str,
        notes: str,
    ) -> Self:
        return cls(
            **cls.database.queryone(
                "INSERT INTO task(user_id, call_id, name, notes, created_at) VALUES (?,?,?,?,?) RETURNING *;",
                (
                    user.id,
                    None if call is None else call.id,
                    name,
                    notes,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        )


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return hasher.verify(password_hash, password)


def create_token(user: User, dur: timedelta, secret: str) -> str:
    return jwt.encode(
        {"user_id": user.id, "exp": datetime.now(timezone.utc) + dur},
        secret,
        algorithm="HS256",
    )


def verify_token(token: str, secret: str) -> int:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload["user_id"]
    except jwt.DecodeError:
        raise ValueError("Invalid token")


app = FastAPI()


LOGIN_HTML = jinja2.Template("""
<html>
    <head>
        <title>Login</title>
    </head>
    <body>
        <h1>Login</h1>
        <form action="/login" method="post">
            <ul>
                <li>
                    <label for="name">Name</label>
                    <input type="text" name="name" id="name" required>
                </li>
                <li>
                    <label for="password">Password</label>
                    <input type="password" name="password" id="password" required>
                <li>
                    <input type="hidden" name="next" value="{{ next }}">
                </li>
                <li>
                    <button type="submit">Login</button>
                </li>
            </ul>
        </form>
    <style>
        html {
            background: black;
            color: white;
        }
        body {
            text-align: center;
        }
        form {
            display: inline-block;
            padding: 1rem;
            border: 1px solid white;
        }
        ul {
            list-style: none;
            padding: 0;
        }
        form li {
            margin: 1rem;
        }
        label {
            display: inline-block;
            text-align: right;
            margin-bottom: 1rem;
        }
        input {
            display: inline-block;
            width: 100%;
            padding: 0.5rem;
            border: 1px solid white;
            background: black;
            color: white;
            font: 1em sans-serif;
            box-sizing: border-box;
        }
        input:focus {
            border-color: yellow;
        }
    </style>
    </body>
</html>
""")


HOMEPAGE_HTML = jinja2.Template("""
<html>
    <head>
        <title>Call Log</title>
    </head>
    <body>
        <div class="section">
            <h2>Calls</h2><a href="/call/create">+</a>
            <ul>
                {% for call in calls %}
                    <li>
                        {{ call.received_at }} - {{ call.caller }} ({{ call.number }})
                        <div>{{ call.notes }}</div>
                    </li>
                {% else %}
                    <li>No calls.</li>
                {% endfor %}
            </ul>
        </div>
        <div class="section">
            <h2>Tasks</h2><a href="/task/create">+</a>
            <ul>
                {% for task in tasks %}
                    <li>
                        <span class="{{ 'completed' if task.completed_at is not none else 'incomplete' }}">{{ task.name }}</span> {{ task.created_at }}
                        <div>{{ task.notes }}</div>
                    </li>
                {% else %}
                    <li>No tasks.</li>
                {% endfor %}
            </ul>
        </div>
        <style>
            html {
                background: black;
                color: white;
            }
            body {
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            a:link, a:visited {
                color: white;
                padding: 0 0.5rem;
                text-decoration: none;
                display: inline-block;
                border: 1px solid transparent;
                font-weight: bold;
            }
            a:hover, a:active {
                border: 1px solid white;
            }
            ul {
                padding: 0.25rem;
                list-style: none;
            }
            .section li + li {
                margin-top: 1rem;
            }
            .section h2 {
                margin: 0;
                padding: 0.25rem;
                position: relative;
                top: 0;
                left: 0;
                background: white;
                color: black;
                transform: translate(-0.25rem, -0.25rem);
                display: inline-block;
            }
            .section a:link, .section a:visited {
                position: absolute;
                top: 0;
                right: 0;
            }
            .section {
                padding: 0.25rem;
                border: 1px solid white;
                margin: 1rem;
                width: 80%;
                min-height: 3rem;
                position: relative;
            }
            .completed {
                text-decoration: line-through;
            }
            .incomplete {
                text-decoration: none;
            }
        </style>
    </body>
</html>
""")

CREATE_CALL_FORM_HTML = jinja2.Template("""
<html>
    <head>
        <title>Create Call</title>
    </head>
    <body>
        <h1>Log Call</h1>
        <form action="/call/create" method="post">
            <ul>
                <li>
                    <label for="received_at">Received At</label>
                    <input type="datetime-local" name="received_at" id="received_at" value="{{ current_datetime.strftime('%Y-%m-%dT%H:%M:%S') }}" required>
                </li>

                <li>
                    <label for="number">Number</label>
                    <input type="text" name="number" id="number" required>
                </li>
                
                <li>
                    <label for="caller">Caller</label>
                    <input type="text" name="caller" id="caller" required>
                </li>

                <li>
                    <label for="notes">Notes</label>
                    <textarea name="notes" id="notes" rows=5></textarea>
                </li>

                <li>
                    <button type="submit">Create Call</button>
                </li>
            </ul>
        </form>
        <style>
            html {
                background: black;
                color: white;
            }
            body {
                text-align: center;
            }
            form {
                display: inline-block;
                padding: 1rem;
                border: 1px solid white;
            }
            ul {
                list-style: none;
                padding: 0;
            }
            form li{
                margin: 1rem;
            }
            label {
                display: inline-block;
                text-align: right;
            }
            input, textarea {
                display: inline-block;
                width: 100%;
                padding: 0.5rem;
                border: 1px solid white;
                background: black;
                color: white;
                font: 1em sans-serif;
                box-sizing: border-box;
            }
            input:focus, textarea:focus {
                border-color: yellow;
            }
            textarea {
                vertical-align: top;
                resize: vertical;
            }
        </style>
    </body>
</html>
""")


CREATE_TASK_FORM_HTML = jinja2.Template("""
<html>
    <head>
        <title>Create Task</title>
    </head>
    <body>
        <h1>Create Task</h1>
        <form action="/task/create" method="post">
            <ul>
                <li>
                    <label for="call_id">Call</label>
                    <select name="call_id" id="call_id">
                        {% for call in calls %}
                            <option value="{{ call.id }}">{{ call.received_at }} - {{ call.caller }} ({{ call.number }})</option>
                        {% endfor %}
                    </select>
                </li>
                <li>
                    <label for="name">Name</label>
                    <input type="text" name="name" id="name" required>
                </li>

                <li>
                    <label for="notes">Notes</label>
                    <textarea name="notes" id="notes" rows=5></textarea>
                </li>

                <li>
                    <button type="submit">Create Task</button>
                </li>
            </ul>
        </form>
        <style>
            html {
                background: black;
                color: white;
            }
            body {
                text-align: center;
            }
            form {
                display: inline-block;
                padding: 1rem;
                border: 1px solid white;
            }
            ul {
                list-style: none;
                padding: 0;
            }
            form li{
                margin: 1rem;
            }
            label {
                display: inline-block;
                text-align: right;
            }
            input, textarea {
                display: inline-block;
                width: 100%;
                padding: 0.5rem;
                border: 1px solid white;
                background: black;
                color: white;
                font: 1em sans-serif;
                box-sizing: border-box;
            }
            input:focus, textarea:focus {
                border-color: yellow;
            }
            textarea {
                vertical-align: top;
                resize: vertical;
            }
        </style>
    </body>
</html>
""")


class LoginRequired(Exception):
    pass


def authenticated(token: Annotated[str | None, Cookie()] = None) -> User:
    try:
        assert token is not None
        return User.get(verify_token(token, jwt_secret))
    except (ValueError, AssertionError):
        raise LoginRequired()


@app.exception_handler(LoginRequired)
def login_required_exception_handler(request: Request, _: LoginRequired):
    return RedirectResponse(f"/login?next={quote(request.url._url)}")


@app.get("/login", response_class=HTMLResponse)
def get_login_page(next: Annotated[str, Query()] = "/"):
    return LOGIN_HTML.render(next=next)


@app.post("/login")
def post_login_page(
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()],
):
    try:
        user = User.login(name, password)
    except ValueError:
        return RedirectResponse(f"/login?next={next!r}")
    response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        "token",
        create_token(user, timedelta(days=1), jwt_secret),
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


@app.get("/", response_class=HTMLResponse)
def get_homepage(_: Annotated[User, Depends(authenticated)]):
    return HOMEPAGE_HTML.render(
        calls=Call.all(),
        tasks=Task.all(),
    )


@app.get("/call/create", response_class=HTMLResponse)
def get_create_call_form(user: Annotated[User, Depends(authenticated)]):
    return CREATE_CALL_FORM_HTML.render(current_datetime=datetime.now().astimezone())


@app.post("/call/create")
def post_create_call_form(
    received_at: Annotated[datetime, Form()],
    number: Annotated[str, Form()],
    caller: Annotated[str, Form()],
    notes: Annotated[str, Form()],
    user: Annotated[User, Depends(authenticated)],
):
    Call.create(received_at.astimezone(), user, number, caller, notes)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@app.get("/task/create", response_class=HTMLResponse)
def get_create_task_form(user: Annotated[User, Depends(authenticated)]):
    return CREATE_TASK_FORM_HTML.render(calls=Call.all())


@app.post("/task/create")
def post_create_task_form(
    name: Annotated[str, Form()],
    notes: Annotated[str, Form()],
    user: Annotated[User, Depends(authenticated)],
    call_id: Annotated[int | None, Form()] = None,
):
    call = Call.get(call_id) if call_id is not None else None
    Task.create(user, call, name, notes)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


if __name__ == "__main__":
    uvicorn.run("call_log:app", host="0.0.0.0", port=8000, reload=True)
