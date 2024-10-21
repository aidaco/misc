from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Annotated
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, Form, Depends, Query, Cookie, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
import jinja2
import uvicorn

import appbase

confconf = appbase.ConfigConfig.load_from(name="call_log")


@confconf.root
class rootconfig:
    datadir: Path = confconf.source.datadir


@confconf.section("auth")
class authconfig:
    jwt_secret: str = "secret"
    jwt_duration: timedelta = timedelta(days=1)


@confconf.section("db")
class config:
    uri: str | Path = rootconfig.datadir / "call_log.sqlite3"


class User(appbase.Model):
    id: appbase.INTPK
    name: str
    password_hash: str
    created_at: datetime
    updated_at: datetime | None


class UserStore(appbase.Table[User, appbase.Database]):
    MODEL = User

    def insert(  # type: ignore
        self,
        name: str,
        password: str,
    ) -> User | None:
        return super().insert(
            (
                name,
                appbase.security.hash_password(password),
                datetime.now(timezone.utc),
            )
        )

    def login(self, name: str, password: str) -> User:
        row = self.select("WHERE name=:name", {"name": name}).one()
        if row is None or not appbase.security.verify_password(
            password, row.password_hash
        ):
            raise ValueError("Login failed.")
        return row


class Call(appbase.Model):
    id: appbase.INTPK
    received_at: datetime
    received_by_id: int
    number: str
    caller: str
    notes: str
    created_at: datetime
    updated_at: datetime | None


class CallStore(appbase.Table[Call, appbase.Database]):
    MODEL = Call

    def insert(  # type: ignore
        self,
        received_at: datetime,
        received_by: User,
        number: str,
        caller: str,
        notes: str,
    ) -> Call | None:
        return super().insert(
            {
                "received_at": received_at,
                "received_by_id": received_by.id,
                "number": number,
                "caller": caller,
                "notes": notes,
                "created_at": datetime.now(timezone.utc),
            }
        )


class Task(appbase.Model):
    id: appbase.INTPK
    user_id: int
    call_id: int | None
    name: str
    notes: str
    created_at: datetime
    updated_at: datetime | None
    completed_at: datetime | None


class TaskStore(appbase.Table[Task, appbase.Database]):
    MODEL = Task

    def insert(  # type: ignore
        self,
        user: User,
        call: Call | None,
        name: str,
        notes: str,
    ) -> Task | None:
        return super().insert(
            {
                "user_id": user.id,
                "call_id": None if call is None else call.id,
                "name": name,
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )


def depends_userstore(request: Request) -> UserStore:
    return request.app.state.users


def depends_callstore(request: Request) -> CallStore:
    return request.app.state.calls


def depends_taskstore(request: Request) -> TaskStore:
    return request.app.state.tasks


Users = Annotated[UserStore, Depends(depends_userstore)]
Tasks = Annotated[TaskStore, Depends(depends_taskstore)]
Calls = Annotated[CallStore, Depends(depends_callstore)]


class LoginRequired(Exception):
    pass


def depends_authentication(
    users: Users, token: Annotated[str | None, Cookie()] = None
) -> User:
    try:
        assert token is not None
        return users.get(appbase.security.verify_token(token, authconfig.jwt_secret))
    except (ValueError, AssertionError):
        raise LoginRequired()


Authenticated = Annotated[User, Depends(depends_authentication)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    with appbase.Database.connect(config.uri) as db:
        app.state.users = UserStore.attach(db)
        app.state.calls = CallStore.attach(db)
        app.state.tasks = TaskStore.attach(db)
        yield


app = FastAPI(lifespan=lifespan)


@app.exception_handler(LoginRequired)
def login_required_exception_handler(request: Request, _: LoginRequired):
    return RedirectResponse(f"/login?next={quote(request.url._url)}")


@app.get("/login", response_class=HTMLResponse)
def get_login_page(next: Annotated[str, Query()] = "/"):
    return LOGIN_HTML.render(next=next)


@app.post("/login")
def post_login_page(
    users: Users,
    name: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()],
):
    try:
        user = users.login(name, password)
    except ValueError:
        return RedirectResponse(f"/login?next={next!r}")
    response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        "token",
        appbase.security.create_token(
            user.id, timedelta(days=1), authconfig.jwt_secret
        ),
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


@app.get("/", response_class=HTMLResponse)
def get_homepage(calls: Calls, tasks: Tasks, _: Authenticated):
    return HOMEPAGE_HTML.render(
        calls=calls,
        tasks=tasks,
    )


@app.get("/call/create", response_class=HTMLResponse)
def get_create_call_form(user: Authenticated):
    return CREATE_CALL_FORM_HTML.render(current_datetime=datetime.now().astimezone())


@app.post("/call/create")
def post_create_call_form(
    user: Authenticated,
    calls: Calls,
    received_at: Annotated[datetime, Form()],
    number: Annotated[str, Form()],
    caller: Annotated[str, Form()],
    notes: Annotated[str, Form()],
):
    calls.insert(
        received_at=received_at.astimezone(),
        received_by=user,
        number=number,
        caller=caller,
        notes=notes,
    )
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


@app.get("/task/create", response_class=HTMLResponse)
def get_create_task_form(_: Authenticated, calls: Calls):
    return CREATE_TASK_FORM_HTML.render(calls=calls)


@app.post("/task/create")
def post_create_task_form(
    user: Authenticated,
    calls: Calls,
    tasks: Tasks,
    name: Annotated[str, Form()],
    notes: Annotated[str, Form()],
    call_id: Annotated[int | None, Form()] = None,
):
    call = calls.get(call_id) if call_id is not None else None
    tasks.insert(user, call, name, notes)
    return RedirectResponse("/", status_code=status.HTTP_302_FOUND)


def serve(host: str = "0.0.0.0", port: int = 8080, reload: bool = True) -> None:
    uvicorn.run("misc.call_log:app", host="0.0.0.0", port=8000, reload=reload)


if __name__ == "__main__":
    serve()

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

# sqlite3.register_adapter(datetime, datetime.isoformat)
# sqlite3.register_converter(
#     "datetime", lambda b: datetime.fromisoformat(b.decode("utf-8"))
# )


# class TableMeta(type):
#     CREATE: ClassVar[str]
#     NAME: ClassVar[str]
#     database: ClassVar["Database"]

#     def __new__(cls, name, bases, dct):
#         instance = super().__new__(cls, name, bases, dct)
#         instance = dataclass(instance)
#         if name != "Table":
#             Database.add_table(instance)
#         return instance

#     @classmethod
#     def set_database(cls, database: "Database") -> None:
#         cls.database = database


# @dataclass
# class Database:
#     uri: str = ":memory:"
#     connection: sqlite3.Connection | None = None
#     connect_config: str = dedent("""
#         PRAGMA journal_mode = WAL;
#         PRAGMA synchronous = normal;
#         PRAGMA temp_store = memory;
#         PRAGMA mmap_size = 30000000000;
#         PRAGMA foreign_keys = on;
#         PRAGMA auto_vacuum = incremental;
#     """)
#     tables: ClassVar[set[type[TableMeta]]] = set()

#     def __post_init__(self) -> None:
#         for table in self.tables:
#             table.set_database(self)

#     def connect(self) -> sqlite3.Connection:
#         if self.connection is None:
#             connection = sqlite3.connect(self.uri)
#             connection.row_factory = sqlite3.Row
#             connection.executescript(self.connect_config)
#             connection.executescript(
#                 ";".join(dedent(table.CREATE) for table in self.tables)
#             )
#             self.connection = connection
#         return self.connection

#     def query(self, query, *args, **kwargs):
#         print(query)
#         with self.connect() as connection:
#             cursor = connection.cursor()
#             cursor.execute(dedent(query), *args, **kwargs)
#             yield from cursor

#     def queryone(self, query, *args, **kwargs):
#         print(query)
#         with self.connect() as connection:
#             cursor = connection.cursor()
#             cursor.execute(dedent(query), *args, **kwargs)
#             return cursor.fetchone()

#     def exec(self, *args, **kwargs):
#         with self.connect() as connection:
#             cursor = connection.cursor()
#             cursor.executescript(*args, **kwargs)

#     @classmethod
#     def add_table[T: type[TableMeta]](cls, table_cls: T) -> T:
#         cls.tables.add(table_cls)
#         return table_cls


# class Table(metaclass=TableMeta):
#     @classmethod
#     def get(cls, id: int) -> Self:
#         return cls(
#             **cls.database.queryone(f"SELECT * FROM {cls.NAME} WHERE id=?", (id,))
#         )

#     @classmethod
#     def all(cls) -> Iterator[Self]:
#         yield from (
#             cls(**row) for row in cls.database.query(f"SELECT * FROM {cls.NAME}")
#         )

#     @classmethod
#     def where(cls, *predicates, **values) -> Iterator[Self]:
#         predicates = [
#             *predicates,
#             *(f"{column}=?" for column in values),
#         ]
#         yield from (
#             cls(**row)
#             for row in cls.database.query(
#                 f"SELECT * FROM {cls.NAME} WHERE {" AND ".join(predicates)}",
#                 tuple(values.values()),
#             )
#         )


# CLOSE_CONFIG = """
# PRAGMA vacuum;
# PRAGMA incremental_vacuum;
# PRAGMA optimize;
# """
