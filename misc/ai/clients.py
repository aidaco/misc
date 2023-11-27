from pathlib import Path
from time import time_ns
from urllib.request import urlopen
from typing import Literal, Protocol, Callable
from dataclasses import dataclass
import json

import openai

from .messages import Message, TextChatMessage, MultiModalChatMessage


class Composer(Protocol):
    def compose(self, role: str, content: str, **kwargs) -> ChatMessage:
        ...


class Completer(Protocol):
    def complete(self, messages: list[ChatMessage]) -> ChatMessage:
        ...


@dataclass
class OpenAITextChatCompleter:
    client: openai.OpenAI
    model: Literal['gpt-4-1106-preview'] = 'gpt-4-1106-preview'
    max_tokens: int = 4096


    def complete(
        self,
        messages: list[TextChatMessage],
    ) -> list[TextChatMessage]:
        completion = (
            self.client.chat.completions.create(
                model=self.model,
                messages=[msg.asdict() for msg in messages],
                max_tokens=self.max_tokens,
            )
            .choices[0]
        )

        match completion.finish_reason:
            case 'stop':
                return [Message.parse(completion.message)]
            case _:
                raise RuntimeWarning(f'Unexpected finish reason: {completion.finish_reason}')


@dataclass
class OpenAIMultiModalChatCompleter:
    client: openai.OpenAI
    model: Literal['gpt-4-1106-preview', 'gpt-4-vision-preview']
    tool_schema: list
    tool_map: dict
    tool_choice: Literal['auto', 'none'] = 'auto'
    max_tokens: int = 4096

    def complete(
        self,
        messages: list[MultiModalChatMessage],
    ) -> list[MultiModalChatMessage]:
        completion = (
            self.client.chat.completions.create(
                model=self.model,
                messages=[msg.asdict() for msg in messages],
                tools=self.tool_schema,
                tool_choice=self.tool_choice,
                max_tokens=self.max_tokens,
            )
            .choices[0]
        )
        message = Message.parse(completion.message)
        match completion.finish_reason:
            case 'stop':
                return [message]
            case 'tool_calls':
                tool_calls = list(self._call_tools(message.tool_calls, tool_map))
                follow_up = self.complete_with_tool_calls(
                    messages+tool_calls,
                    tool_schema,
                    tool_map,
                    tool_choice
                )
                return [
                    message,
                    *tool_calls,
                    *follow_up
                ]

    def _call_tools(self, tool_calls: list, tool_map: dict[str, Callable]):
        for fncall in tool_calls:
            try:
                name = fncall.function.name
                fn = tool_map[name]
                args = json.loads(fncall.function.arguments)
                result = fn(**args)
                yield Message.construct(
                    tool_call_id=fncall.id,
                    role="tool",
                    name=name,
                    content=result,
                )
            except Exception:
                pass

class OpenAIClient:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        chat_model: Literal['gpt-4-1106-preview', 'gpt-4-vision-preview'] = 'gpt-4-vision-preview',
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
