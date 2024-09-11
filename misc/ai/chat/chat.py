import json

from rich import print
from typer import Typer
from dataclasses import dataclass

import openai

from .composers import ComposeText, ComposeMultiModal
from .clients import OpenAIClient
from .completers import OpenAITextChatCompleter, OpenAIMultiModalChatCompleter
from .messages import (
    MessageProvider,
    Messages,
    TextWithToolsChatMessage,
    MultiModalWithToolsChatMessage,
)


@dataclass
class Chat[MessageType]:
    messages: Messages[MessageType]
    composer: MessageProvider[MessageType]
    completer: MessageProvider[MessageType]

    @staticmethod
    def text(
        tool_schema: list | openai._types.NotGiven = openai._types.NOT_GIVEN,
        tool_map: dict | openai._types.NotGiven = openai._types.NOT_GIVEN,
    ) -> "Chat[TextWithToolsChatMessage]":
        return Chat(
            Messages([], []),
            ComposeText(),
            OpenAITextChatCompleter(
                openai.OpenAI(),
                tool_schema=tool_schema,
                tool_map=tool_map,
            ),
        )

    @staticmethod
    def multimodal() -> "Chat[MultiModalWithToolsChatMessage]":
        return Chat(
            Messages([], []),
            ComposeMultiModal(),
            OpenAIMultiModalChatCompleter(openai.OpenAI()),
        )

    def run(self):
        compose = self.composer.provide
        complete = self.completer.provide
        try:
            self.message(compose, "system")
            while True:
                self.message(compose, "user")
                self.message(complete, "assistant")
        except KeyboardInterrupt:
            print("Exit.")

    def message(self, provider, role: str):
        for message in provider(role, self.messages):
            self.messages.post(message)


cli = Typer()


@cli.command()
def chat():
    Chat.text().run()


@cli.command()
def imgen():
    client = OpenAIClient(chat_model="gpt-4-1106-preview")
    tool_schema = [
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
                        "size": {
                            "type": "string",
                            "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        },
                        "quality": {"type": "string", "enum": ["standard", "hd"]},
                        "style": {"type": "string", "enum": ["vivid", "natural"]},
                    },
                    "required": ["prompt"],
                },
            },
        }
    ]
    tool_map = {
        "generate_image": client.generate_image,
    }
    Chat.text(tool_schema=tool_schema, tool_map=tool_map).run()


if __name__ == "__main__":
    cli()
