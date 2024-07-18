from pathlib import Path
from dataclasses import dataclass
import sqlite3
from typing import Iterator, Self
from functools import cache
from contextlib import contextmanager
import random
import time
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from openai import OpenAI
from pydantic import TypeAdapter
import requests

WD = Path.home() / "Documents" / "GameContent"
WD.mkdir(exist_ok=True, parents=True)

TASKS = []
TASK_DELAY = 0
live = None


@contextmanager
def task(text: str):
    spinner = Spinner("dots", text=text)
    TASKS.append(spinner)
    try:
        time.sleep(TASK_DELAY)
        yield
    finally:
        TASKS.remove(spinner)


def show(*args, **kwargs):
    if live:
        live.console.print(*args, **kwargs)
    else:
        __builtins__.print(*args, **kwargs)


@contextmanager
def show_tasks():
    global live
    live = Live(
        get_renderable=lambda: Group(*TASKS), transient=True, refresh_per_second=60
    )
    with live:
        yield


def DEFAULT_MESSAGES():
    type = random.choice(
        "characters,items,abilities,weapons,entities,enemies,buildings,historical events".split(
            ","
        )
    )
    return [
        {
            "role": "system",
            "content": """\
    You are a sophisticated creative writing assistant for video game content.\
    Help us create some fun characters, items, abilities, weapons, entities, enemies, buildings, historical events, etc. \
    For each creation, provide a type, name, description and an image generation prompt. \
    Respond with JSON objects of the form {"type": "...", "name": "...", "description": "...", "image": "..."}.\
    """,
        },
        {
            "role": "user",
            "content": """\
    We're creating a location based cooperative multiplayer game. \
    In this game players collaborate to push back the darkness. \
    The tone of the game is dark but lighthearted.\
    The game features a simple web-based interface. \
    Create an entity.\
     """,
        },
        {
            "role": "assistant",
            "content": """{ "type": "entity", "name": "Luminosphere", "description": "A floating, crystalline orb that emits a soft, warm light. It's a source of strength for all players within its vicinity, amplifying their abilities and repelling the darkness.", "image_prompt": "A levitating, clear crystal orb radiating a gentle, warm glow. The orb has intricate, engraved patterns and emits a soft hum." }""",
        },
        {"role": "user", "content": "Perfect, now an enemy."},
        {
            "role": "assistant",
            "content": """{ "type": "enemy", "name": "Shade", "description": "Stealthy and agile enemies that strike from the shadows. They are hard to detect and even harder to catch, making them a dangerous threat.", "image_prompt": "Sleek, humanoid figures wrapped in dark, cloaking garments. They move silently and have piercing, glowing eyes that are the only visible parts of their faces." }""",
        },
        {"role": "user", "content": "Great, next a historical event."},
        {
            "role": "assistant",
            "content": """{ "type": "historical event", "name": "The Great Eclipse", "description": "A cataclysmic event when darkness first descended upon the world. During the Great Eclipse, countless light sources were extinguished, and many heroes were lost.", "image_prompt": "A dramatic, dark landscape with the sun completely covered by a black disk. Shadows stretch across the land, and people are depicted in despair." }""",
        },
        {
            "role": "user",
            "content": f"Excellent, produce a {type}",
        },
    ]


def generate_image(openai: OpenAI, prompt: str) -> bytes:
    with task("Call dall-e-3..."):
        response = openai.images.generate(
            model="dall-e-3", prompt=prompt, quality="hd", n=1, size="1024x1024"
        )
        url = response.data[0].url
        assert url is not None
        with task("Retrieve image..."):
            return requests.get(url).content


def generate_object[T](
    openai: OpenAI,
    messages: list[dict],
    model: type[T],
) -> T:
    with task("Call GPT-4o..."):
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            response_format={"type": "json_object"},
        )
        json = response.choices[0].message.content
        with task("Validate response..."):
            return TypeAdapter(model).validate_json(json)


@cache
def connect(uri: str | Path = WD / "database1.sqlite3") -> sqlite3.Connection:
    with task("Connect database..."):
        connection = sqlite3.connect(uri, isolation_level=None)
        connection.row_factory = sqlite3.Row
        with connection:
            connection.execute("begin")
            connection.execute(GameComponentRow.CREATE)
            connection.execute(GameComponentImage.CREATE)
            connection.executescript(
                "pragma journal_mode = WAL;"
                "pragma synchronous = normal;"
                "pragma temp_store = memory;"
                "pragma mmap_size = 30000000000;"
                "pragma foreign_keys = on;"
                "pragma auto_vacuum = incremental;"
                "pragma foreign_keys = on;"
            )
        return connection


@dataclass
class GameComponentData:
    type: str
    name: str
    description: str
    image_prompt: str

    @classmethod
    def generate(cls, openai: OpenAI) -> Self:
        with task("Generate GameComponentData..."):
            return generate_object(openai, DEFAULT_MESSAGES(), cls)


@dataclass
class GameComponentImage:
    CREATE = """
    create table if not exists game_component_image(
        id integer primary key autoincrement,
        component_id integer not null references game_component(id) on update cascade on delete cascade,
        path text not null
    )"""
    id: int
    component_id: int
    path: Path

    @classmethod
    def parse(cls, row: sqlite3.Row) -> Self:
        with task("Parse image..."):
            return cls(
                id=row["id"], component_id=row["component_id"], path=Path(row["path"])
            )

    @classmethod
    def get(cls, id: int) -> Self:
        with task("Get image..."):
            connection = connect()
            return cls.parse(
                connection.execute(
                    "select * from game_component_image where id=:id", {"id": id}
                ).fetchone()
            )

    @classmethod
    def iter_by_component_id(cls, component_id: int) -> Iterator[Self]:
        with task("Iter images for component..."):
            connection = connect()
            for i, row in enumerate(
                connection.execute(
                    "select * from game_component_image where component_id=:component_id",
                    {"component_id": component_id},
                )
            ):
                with task(f"[{i}]"):
                    yield cls.parse(row)

    @classmethod
    def insert(cls, component_id: int, path: Path) -> Self:
        with task("Insert image..."):
            connection = connect()
            with connection:
                row = connection.execute(
                    "insert into game_component_image(component_id, path) values (:component_id, :path) returning *",
                    {"component_id": component_id, "path": str(path.resolve())},
                ).fetchone()
                return cls.parse(row)


@dataclass
class GameComponentRow:
    CREATE = "create table if not exists game_component(id integer primary key autoincrement, type text not null, name text not null, description text not null, image_prompt text not null)"
    id: int
    type: str
    name: str
    description: str
    image_prompt: str

    @property
    def images(self) -> Iterator[GameComponentImage]:
        with task("Load images..."):
            return GameComponentImage.iter_by_component_id(self.id)

    @classmethod
    def webview(cls) -> str:
        data = "".join(f"<li>{row.html()}</li>" for row in cls.iter())
        return f"<ul>{data}</ul>"

    def html(self) -> str:
        images = "".join(
            f'<li><img src="/{img.path.relative_to(WD)}"></li>' for img in self.images
        )
        return f"""
        <style>
            :root {{
                background: black;
                color: white;
                font: 28px sans-serif;
            }}
            div {{
               display: grid;
               grid-template-columns: 60% 30%; 
               margin: 5%;
               overflow-auto;
            }}

            img {{
                object-fit: contain;
                margin: 1rem;
                max-width: 512px;
                max-height: 512px;
            }}

            .images {{
                display: flex;
                flex-direction: row;
            }}
        </style>
        <div>
            <ul>
                <li>{self.id}</li>
                <li>{self.name}</li>
                <li>{self.description}</li>
                <li>{self.image_prompt}</li>
            </ul>
            <ul class="images">
                {images}
            </ul>
        </div>
        <hr>"""

    def __rich__(self) -> RenderableType:
        return Panel(
            Group(
                str(self.id), self.type, self.name, self.description, self.image_prompt
            )
        )

    @classmethod
    def parse(cls, row: sqlite3.Row) -> Self:
        with task("Parse GameComponentRow..."):
            return cls(**row)

    @classmethod
    def iter(cls) -> Iterator[Self]:
        with task("Iterate GameComponentRow..."):
            connection = connect()
            with connection:
                for i, row in enumerate(
                    connection.execute("select * from game_component", {})
                ):
                    with task(f"[{i}]"):
                        yield cls.parse(row)

    @classmethod
    def insert(cls, type: str, name: str, description: str, image_prompt: str) -> Self:
        with task("Insert GameComponentRow..."):
            connection = connect()
            with connection:
                row = connection.execute(
                    "insert into game_component(type, name, description, image_prompt) values (:type, :name, :description, :image_prompt) returning *",
                    {
                        "type": type,
                        "name": name,
                        "description": description,
                        "image_prompt": image_prompt,
                    },
                ).fetchone()
                return cls.parse(row)

    def generate_image(self, openai: OpenAI) -> GameComponentImage:
        with task("Generate Image..."):
            data = generate_image(openai, self.image_prompt)
            with task("Write image..."):
                path = (
                    WD / f"{self.name} {datetime.now(tz=timezone.utc).timestamp()}.png"
                )
                path.write_bytes(data)
            with task("Save data..."):
                return GameComponentImage.insert(self.id, path)

    @classmethod
    def generate(cls, openai: OpenAI) -> Self:
        with task("Generate GameComponentRow..."):
            item = GameComponentData.generate(openai)
            with task("Save GameComponentRow..."):
                return cls.insert(
                    item.type,
                    item.name,
                    item.description,
                    item.image_prompt,
                )

    @classmethod
    def generate_n(cls, openai: OpenAI, n: int = 5) -> Iterator[Self]:
        for i in range(n):
            with task(f"[{i+1}/{n}]"):
                yield cls.generate(openai)


def api():
    app = FastAPI()

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(GameComponentRow.webview())

    app.mount("/", StaticFiles(directory=WD))

    uvicorn.run(app, host="localhost", port=8000)


def main(openai: OpenAI | None = None):
    with show_tasks():
        openai = openai if openai is not None else OpenAI()
        for row in GameComponentRow.generate_n(openai, 2):
            show(row)
            row.generate_image(openai)


if __name__ == "__main__":
    main()
