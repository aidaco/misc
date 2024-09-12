from typing import Iterator
import os
import io

from openai import OpenAI
from pydantic import BaseModel
import requests
from PIL import Image

from misc.ai.chat import Chat
from misc.ai.dalle3 import Image as ImageGen

openai = OpenAI()
chat = Chat(client=openai).system("You are an expert graphic design assitant.")
output_directory = "output"
convert_svg = True

# Ensure the output directory exists
os.makedirs(output_directory, exist_ok=True)


class StickerDesignModel(BaseModel):
    design: str


class StickerListModel(BaseModel):
    stickers: list[StickerDesignModel]


def generate_stickers(n: int = 5) -> Iterator[ImageGen]:
    for sticker in (
        chat.user(
            f"Generate {n} creative ideas for specific sticker designs of at least 5 sentences."
        )
        .model(StickerListModel)
        .stickers
    ):
        yield ImageGen.new(prompt=sticker.design)


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


def save_image(image: Image.Image, prompt, idx):
    base_filename = os.path.join(output_directory, f"sticker_{idx}")
    png_path = f"{base_filename}.png"
    image.save(png_path)

    if convert_to_svg:
        svg_data = convert_to_svg(image)
        svg_path = f"{base_filename}.svg"
        with open(svg_path, "wb") as svg_file:
            svg_file.write(svg_data)


def main(n: int = 5):
    images = generate_stickers(n)
    for idx, imagegen in enumerate(images):
        image = Image.open(imagegen.generate())
        image_no_bg = remove_background(image)
        save_image(image_no_bg, imagegen.prompt, idx)
        print(imagegen.prompt)


if __name__ == "__main__":
    main()
