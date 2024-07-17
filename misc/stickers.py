from dataclasses import dataclass, field
import io
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
import json
import time

from rich.spinner import Spinner
from rich.live import Live
from rich import print
from PIL import Image
import rembg
from openai import OpenAI
import requests

output_directory = Path("stickers")
output_directory.mkdir(exist_ok=True)
db = sqlite3.connect(output_directory / "sticker.sqlite3", isolation_level=None)
db.row_factory = sqlite3.Row
db.executescript("""
PRAGMA foreign_keys=on;
PRAGMA journal_mode=wal;
CREATE TABLE IF NOT EXISTS sticker(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    generation_settings TEXT
);
""")
openai = OpenAI()


@dataclass
class Sticker:
    id: int
    prompt: str
    generated_at: datetime
    generation_settings: dict = field()

    @property
    def path(self) -> Path:
        return output_directory / f"sticker_{self.id}.png"

    @classmethod
    def create(cls, prompt: str, generation_settings: dict):
        row = db.execute(
            "INSERT INTO sticker(prompt, generated_at, generation_settings) VALUES (:prompt,:generated_at,:generation_settings) RETURNING *;",
            {
                "prompt": prompt,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "generation_settings": json.dumps(generation_settings),
            },
        ).fetchone()
        if row is None:
            return row
        return cls(
            id=row["id"],
            prompt=row["prompt"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            generation_settings=json.loads(row["generation_settings"]),
        )


def generate_sticker_prompt(
    system: str = "You are a large language model that creates prompts for AI image generation based on user specification. Use visual language and extreme detail when writing the prompt. Only describe images that strictly fit within the canvas.",
    prompt: str = "Create a new sticker. Creative, popular, solid color background, thin border around the main subject.",
) -> tuple[str, dict]:
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    settings = dict(
        model="dall-e-3", quality="hd", style="vivid", n=1, size="1792x1024"
    )
    return response.choices[0].message.content, settings  # type: ignore


def generate_sticker_image(prompt, settings) -> bytes:
    response = openai.images.generate(prompt=prompt, **settings)
    url = response.data[0].url
    assert url is not None
    return requests.get(url).content


def remove_background(data: bytes) -> bytes:
    return rembg.remove(data)  # type: ignore


def convert_to_svg(data: bytes) -> bytes:
    import potrace

    image = Image.open(io.BytesIO(data))
    trace = potrace.Bitmap(image).trace(
        turdsize=2,
        turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
        alphamax=1,
        opticurve=False,
        opttolerance=0.2,
    )

    fp = io.StringIO()
    fp.write(
        f"""<svg version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{image.width}" height="{image.height}" viewBox="0 0 {image.width} {image.height}">"""
    )
    parts = []
    for curve in trace:
        fs = curve.start_point
        parts.append(f"M{fs.x},{fs.y}")
        for segment in curve.segments:
            if segment.is_corner:
                a = segment.c
                b = segment.end_point
                parts.append(f"L{a.x},{a.y}L{b.x},{b.y}")
            else:
                a = segment.c1
                b = segment.c2
                c = segment.end_point
                parts.append(f"C{a.x},{a.y} {b.x},{b.y} {c.x},{c.y}")
        parts.append("z")
    fp.write(
        f'<path stroke="none" fill="black" fill-rule="evenodd" d="{"".join(parts)}"/>'
    )
    fp.write("</svg>")

    return fp.getvalue().encode()


def generate_sticker():
    start = time.perf_counter()
    with Live(refresh_per_second=10, transient=True) as live:
        live.update(Spinner("dots", "Generating prompt..."))
        prompt, settings = generate_sticker_prompt()

        live.update(Spinner("dots", "Generating image..."))
        image = generate_sticker_image(prompt, settings)

        live.update(Spinner("dots", "Removing background..."))
        image_nobg = remove_background(image)

        live.update(Spinner("dots", "Saving..."))
        sticker = Sticker.create(prompt, settings)
        sticker.path.write_bytes(image)
        sticker.path.with_stem(f"{sticker.path.stem}_nobg").write_bytes(image_nobg)
    delta = time.perf_counter() - start
    print(f"[green]Generated sticker {sticker.id} in {delta:.2f}s.[/]")


def main():
    for _ in range(5):
        generate_sticker()


if __name__ == "__main__":
    main()
