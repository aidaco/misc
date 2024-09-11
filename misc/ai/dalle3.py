from pathlib import Path
from typing import Literal, Self, Iterator
from time import time_ns
from datetime import datetime
import json
import urllib.request
from dataclasses import dataclass, field, asdict
import copy

from pydantic import BaseModel
from typer import Typer
from openai import OpenAI


key = open("/home/tuesday/documents/Secrets/openai-api-key").read().strip()
client = OpenAI(api_key=key)

OUTDIR = Path("results")


class Prompt(BaseModel):
    prompt: str
    model: Literal["dall-e-3"] = "dall-e-3"
    size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1792x1024"
    quality: Literal["standard", "hd"] = "hd"
    style: Literal["vivid", "natural"] = "vivid"


class Prompts(BaseModel):
    prompts: list[Prompt]


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
class Parameters:
    prompt: str
    model: Literal["dall-e-3"] = "dall-e-3"
    size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1792x1024"
    quality: Literal["standard", "hd"] = "hd"
    style: Literal["vivid", "natural"] = "vivid"

    def variations(self, n: int = 5) -> Iterator[Self]:
        response = (
            client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": VARIATIONS_PROMPT},
                    {
                        "role": "user",
                        "content": f"Produce {n} variations of this prompt: {self}",
                    },
                ],
                response_format=Prompts,
            )
            .choices[0]
            .message
        )

        if response.refusal:
            raise ValueError(f"Refusal: {response.refusal}")

        for prompt in response.parsed.prompts:
            yield Parameters(**prompt.model_dump())


@dataclass
class ImageGen:
    batch: list[Parameters]
    output_dir: Path = field(default_factory=Path.cwd)
    output_tag: str = field(default_factory=lambda: f"{time_ns():x}")

    def moderate(self) -> bool:
        response = client.moderations.create(input="prompt").results[0]
        return not response.flagged

    def generate(self):
        for i, params in enumerate(self.batch):
            url = client.images.generate(**asdict(params)).data[0].url
            with urllib.request.urlopen(url) as remote:
                with (self.output_dir / f"{self.output_tag}-{i}.png").open(
                    "wb"
                ) as local:
                    local.write(remote.read())

    def update_metadata(self):
        with (self.output_dir / f"{self.output_tag}.txt").open("a") as metafd:
            for params in self.batch:
                metafd.write(json.dumps(asdict(params)) + "\n")

    def variations(self, index: int = 0, n: int = 5) -> None:
        self.batch.extend(self.batch[index].variations(n))


cli = Typer()


@cli.command()
def single(prompt: str):
    gen = ImageGen([Parameters(prompt)])
    if not gen.moderate():
        raise ValueError("bad prompt")
    gen.generate()
    gen.update_metadata()


@cli.command()
def variations(prompt: str):
    gen = ImageGen([Parameters(prompt)])
    if not gen.moderate():
        raise ValueError("bad prompt")
    gen.variations()
    gen.generate()
    gen.update_metadata()


if __name__ == "__main__":
    cli()
