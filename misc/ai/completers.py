from pathlib import Path
from time import time_ns
from urllib.request import urlopen
from typing import Literal, Protocol
import json

import openai

from .messages import Message


class Client(Protocol):
    def complete_chat(self, messages: list[Message]) -> Message:
        ...

    def generate_image(
        self,
        prompt: str,
        size: Literal['1024x1024', '1792x1024', '1024x1792'] = '1792x1024',
        quality: Literal['standard', 'hd'] = 'hd',
        style: Literal['vivid', 'natural'] = 'natural',
    ):
        ...


class OpenAIClient:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        chat_model: Literal['gpt-4-1106-preview', 'gpt-4-vision-preview'] = 'gpt-4-vision-preview',
        image_model: Literal['dall-e-3',  'dall-e-2'] = 'dall-e-3',
        image_output_dir: Path = Path.cwd(),
        max_tokens: int = 4096,
    ):
        self.client = client if client is not None else openai.OpenAI()
        self.chat_model = chat_model
        self.image_model = image_model
        self.image_output_dir = image_output_dir
        self.max_tokens = max_tokens

    def complete(self, messages: list[Message]) -> Message:
        completion = (
            self.client.chat.completions.create(
                model=self.model,
                messages=[msg.asdict() for msg in messages],
                max_tokens=self.max_tokens,
            )
            .choices[0]
            .message
        )
        return Message.parse(completion)

    def complete_with_tool_calls(self, messages: list[Message], tool_schema, tool_map) -> list[Message]:
        completion = (
            self.client.chat.completions.create(
                model=self.model,
                messages=[msg.asdict() for msg in messages],
                tools=tool_schema,
                tool_choice="auto",
                max_tokens=self.max_tokens,
            )
            .choices[0]
            .message
        )
        tool_calls = getattr(completion, "tool_calls", None)
        if not tool_calls:
            return Message.parse(completion), []

        called_tools = []
        for fncall in tool_calls:
            try:
                name = fncall.function.name
                fn = tool_map[name]
                args = json.loads(fncall.function.arguments)
                result = fn(**args)
                called_tools.append(dict(
                    tool_call_id=fncall.id,
                    role="tool",
                    name=name,
                    content=result,
                
                ))
            except Exception:
                pass
        return completion, called_tools

    def generate_image(
        self,
        prompt: str,
        size: Literal['1024x1024', '1792x1024', '1024x1792'] = '1792x1024',
        quality: Literal['standard', 'hd'] = 'hd',
        style: Literal['vivid', 'natural'] = 'vivid',
    ):

        tag = f'{time_ns():x}'
        parameters = dict(
            model=self.image_model,
            prompt=prompt,
            size=size,
            quality=quality,
        )

        url = self.client.images.generate(
            **parameters,
            n=1
        ).data[0].url
        img_path = self.image_output_dir / f'{tag}.png'
        with urlopen(url) as remote, img_path.open('wb') as local:
            local.write(remote.read())
        with (self.image_output_dir/f'{tag}.txt').open('w') as prompt_store:
            prompt_store.writelines([
                '{',
                *(
                    '\t'f"'{k}': '{v}'" for k, v in parameters.items()
                ),
                '}',
            ])
        return img_path


tools = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Create an image from a prompt using a generative AI model.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The prompt that the image generation model will create an image from.",
                    },
                    "size": {"type": "string", "enum": ['1024x1024', '1792x1024', '1024x1792']},
                    "quality": {"type": "string", "enum": ['standard', 'hd']},
                    "style": {"type": "string", "enum": ['vivid', 'natural']},
                },
                "required": ["prompt"],
            },
        },
    }
]
