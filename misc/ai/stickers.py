from dataclasses import dataclass, field
from typing import Iterator
import os
import io
from pathlib import Path

from pydantic import BaseModel
import requests
from PIL import Image

from misc.ai.chat import Chat
from misc.ai.image import Image as ImageGen


class StickerDesignModel(BaseModel):
    design: str


class StickerListModel(BaseModel):
    stickers: list[StickerDesignModel]


def remove_background(image: Image.Image) -> Image.Image:
    output = io.BytesIO()
    image.save(output, format="PNG")
    response = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": output.getvalue()},
        data={"size": "auto"},
        headers={"X-Api-Key": remove_bg_api_key},
    )
    if response.status_code == requests.codes.ok:
        return Image.open(io.BytesIO(response.content))
    else:
        response.raise_for_status()
        raise Exception()


def convert_to_svg(image: Image.Image) -> bytes:
    import cairosvg

    output = io.BytesIO()
    image.save(output, format="PNG")
    png_data = output.getvalue()
    svg_data = cairosvg.png2svg(bytestring=png_data)
    return svg_data


def save_image(dir: Path, image: Image.Image, prompt, idx):
    path = dir / f"sticker_{idx}.png"
    image.save(path)
    print(path)

    if convert_to_svg:
        svg_data = convert_to_svg(image)
        svg_path = path.with_suffix(".svg")
        svg_path.write_bytes(svg_data)
        print(svg_path)


@dataclass
class Stickers:
    dir: Path = field(default_factory=Path.cwd)
    convert_svg: bool = True
    chat: Chat = field(
        default_factory=lambda: Chat().system(
            "You are an expert graphic design assitant."
        )
    )

    def generate(self, n: int = 5) -> Iterator[ImageGen]:
        for sticker in (
            self.chat.user(
                f"Generate {n} creative ideas for specific sticker designs of at least 5 sentences."
            )
            .model(StickerListModel)
            .stickers
        ):
            print(sticker.design)
            yield ImageGen.new(prompt=sticker.design)

    def save(self, n: int = 5) -> None:
        images = self.generate(n)
        for idx, imagegen in enumerate(images):
            image = Image.open(imagegen.generate())
            image_no_bg = remove_background(image)
            save_image(self.dir, image_no_bg, imagegen.prompt, idx)


if __name__ == "__main__":
    Stickers().save(5)
