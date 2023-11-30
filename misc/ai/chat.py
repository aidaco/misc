import json

from rich import print
from typer import Typer
from dataclasses import dataclass

import openai

from .composers import ComposeText, ComposeMultiModal
from .completers import OpenAITextChatCompleter, OpenAIMultiModalChatCompleter
from .messages import MessageProvider, Messages, construct, TextWithToolsChatMessage, MultiModalWithToolsChatMessage


@dataclass
class Chat[MessageType]:
    messages: Messages[MessageType]
    composer: MessageProvider[MessageType]
    completer: MessageProvider[MessageType]

    @staticmethod
    def text() -> 'Chat[TextChatMessage]':
        return Chat(Messages([], []), ComposeText(), OpenAITextChatCompleter(openai.OpenAI()))

    @staticmethod
    def multimodal() -> 'Chat[MultiModalChatMessage]':
        return Chat(Messages([], []), ComposeMultiModal(), OpenAIMultiModalChatCompleter(openai.OpenAI()))

    def run(self):
        compose = self.composer.provide
        complete = self.completer.provide
        try:
            self.message(compose, 'system')
            while True:
                self.message(compose, 'user')
                self.message(complete, 'assistant')
        except KeyboardInterrupt:
            print("Exit.")

    def message(self, provider, role: str):
        for message in provider(role, self.messages):
            self.messages.post(message)



cli = Typer()

@cli.command()
def chat():
    Chat().run()


@cli.command()
def imgen():
    client = OpenAIClient(chat_model='gpt-4-1106-preview')
    ChatTools(
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
                            "size": {"type": "string", "enum": ['1024x1024', '1792x1024', '1024x1792']},
                            "quality": {"type": "string", "enum": ['standard', 'hd']},
                            "style": {"type": "string", "enum": ['vivid', 'natural']},
                        },
                        "required": ["prompt"],
                    },
                },
            }
        ],
        tool_map={
            'generate_image': client.generate_image,
        }
    ).run()


if __name__ == '__main__':
    cli()
