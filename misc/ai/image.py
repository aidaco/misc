from pathlib import Path
from typing import BinaryIO, Literal, Self, Iterator
from time import time_ns
import json
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
import io

from pydantic import BaseModel
from typer import Typer
from openai import OpenAI

from misc.ai.chat import Chat


key = open("/home/tuesday/documents/Secrets/openai-api-key").read().strip()
client = OpenAI(api_key=key)
chat = Chat.new(client=client)

OUTDIR = Path("results")


class PromptModel(BaseModel):
    prompt: str
    model: Literal["dall-e-3"] = "dall-e-3"
    size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1792x1024"
    quality: Literal["standard", "hd"] = "hd"
    style: Literal["vivid", "natural"] = "vivid"


class PromptListModel(BaseModel):
    prompts: list[PromptModel]


VARIATIONS_PROMPT = """
You are a helpful assistant that generates, optimizes, and improves prompts for AI image generation models. Prompts must be 100-200 words and highly detailed.
Be Specific and Detailed: The more specific your prompt, the better the image quality. Include details like the setting, objects, colors, mood, and any specific elements you want in the image.
Mood and Atmosphere: Describe the mood or atmosphere you want to convey. Words like “serene,” “chaotic,” “mystical,” or “futuristic” can guide the AI in setting the right tone.
Use Descriptive Adjectives: Adjectives help in refining the image. For example, instead of saying “a dog,” say “a fluffy, small, brown dog.”
Consider Perspective and Composition: Mention if you want a close-up, a wide shot, a bird’s-eye view, or a specific angle. This helps in framing the scene correctly.
Specify Lighting and Time of Day: Lighting can dramatically change the mood of an image. Specify if it’s day or night, sunny or cloudy, or if there’s a specific light source like candlelight or neon lights.
Incorporate Action or Movement: If you want a dynamic image, describe actions or movements. For instance, “a cat jumping over a fence” is more dynamic than just “a cat.”
Avoid Overloading the Prompt: While details are good, too many can confuse the AI. Try to strike a balance between being descriptive and being concise.
Use Analogies or Comparisons: Sometimes it helps to compare what you want with something well-known, like “in the style of Van Gogh” or “resembling a scene from a fantasy novel.”
Specify Desired Styles or Themes: If you have a particular artistic style or theme in mind, mention it. For example, “cyberpunk,” “art deco,” or “minimalist.”
Iterative Approach: Sometimes, you may not get the perfect image on the first try. Use the results to refine your prompt and try again.
"""


@dataclass
class Prompt:
    prompt: str
    model: Literal["dall-e-3"] = "dall-e-3"
    size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1792x1024"
    quality: Literal["standard", "hd"] = "hd"
    style: Literal["vivid", "natural"] = "vivid"

    def variations(self, n: int = 5) -> Iterator[Self]:
        response = (
            chat.system(VARIATIONS_PROMPT)
            .user(f"Produce {n} variations of this prompt: {self}")
            .model(PromptListModel)
        )

        for prompt in response.prompts:
            yield Prompt(**prompt.model_dump())

    def generate(self, client: OpenAI, file: BinaryIO) -> None:
        url = client.images.generate(**asdict(self)).data[0].url
        with urllib.request.urlopen(url) as remote:
            file.write(remote.read())


@dataclass
class Image:
    prompt: Prompt

    @classmethod
    def new(cls, **prompt_kwargs) -> Self:
        return cls(prompt=Prompt(**prompt_kwargs))

    def generate(self, file: BinaryIO | None = None) -> BinaryIO:
        if file is None:
            file = io.BytesIO()
        prompt.generate(client, file)
        return file

    def save(self, path: Path | None = None) -> Path:
        if path is None:
            path = Path.cwd() / f"{time_ns()}.png"

        with path.open("wb") as file:
            self.generate(file)
        self.update_metadata(path)
        return path

    def moderate(self) -> None:
        submission = json.dumps(asdict(self.prompt))
        response = client.moderations.create(input=submission).results[0]
        if response.flagged:
            raise ValueError(f"Bad prompt: {self.prompt}")

    def update_metadata(self, path: Path):
        metapath = path.parent / "img_gen_data.jsonl"
        data = json.dumps({"name": path.name, "prompt": asdict(self.prompt)}) + "\n"
        with metapath.open("a") as metafd:
            metafd.write(data)

    def variations(self, n: int = 5) -> Iterator[Self]:
        for prompt in self.prompt.variations(n):
            yield type(self)(prompt=prompt)


cli = Typer()


@cli.command()
def prompt(prompt: str):
    print(Image.new(prompt=prompt).save())


@cli.command()
def variations(base: str, n: int = 5):
    for image in Image.new(prompt=base).variations(n):
        print(image.save())


if __name__ == "__main__":
    cli()
