from pathlib import Path
from time import time_ns
from urllib.request import urlopen
from typing import Literal

import openai

# from .messages import TextChatMessage, MultiModalChatMessage


class OpenAIClient:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        chat_model: Literal[
            "gpt-4-1106-preview", "gpt-4-vision-preview"
        ] = "gpt-4-vision-preview",
        image_model: str = "dalle-3",
        image_output_dir: Path = Path.cwd(),
        max_tokens: int = 4096,
    ):
        self.client = client if client is not None else openai.OpenAI()
        self.chat_model = chat_model
        self.image_model = image_model
        self.image_output_dir = image_output_dir
        self.max_tokens = max_tokens

    def generate_image(
        self,
        prompt: str,
        size: Literal["1024x1024", "1792x1024", "1024x1792"] = "1792x1024",
        quality: Literal["standard", "hd"] = "hd",
        style: Literal["vivid", "natural"] = "vivid",
    ):
        tag = f"{time_ns():x}"
        parameters = dict(
            model=self.image_model,
            prompt=prompt,
            size=size,
            quality=quality,
        )

        url = self.client.images.generate(**parameters, n=1).data[0].url
        img_path = self.image_output_dir / f"{tag}.png"
        with urlopen(url) as remote, img_path.open("wb") as local:
            local.write(remote.read())
        with (self.image_output_dir / f"{tag}.txt").open("w") as prompt_store:
            prompt_store.writelines(
                [
                    "{",
                    *("\t" f"'{k}': '{v}'" for k, v in parameters.items()),
                    "}",
                ]
            )
        return img_path
