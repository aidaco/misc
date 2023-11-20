import openai
from typing import Literal

from .messages import Message


class OpenAICompleter:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        model: Literal['gpt-4-1106-preview', 'gpt-4-vision-preview'] = 'gpt-4-vision-preview',
        max_tokens: int = 4096,
    ):
        self.client = client if client is not None else openai.OpenAI()
        self.model = model
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
