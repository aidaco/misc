import json

from rich import print
from typer import Typer

from .clients import OpenAIClient, Client, Completer
from .messages import Messages, compose


@dataclass
class Chat:
    messages: Messages
    completer: Completer

    def run(self):
        try:
            self.system(self.default_initial_system)
            while True:
                self.user()
                self.complete()
        except KeyboardInterrupt:
            print("Exit.")


    def system(self, message=""):
        self.messages.post(
            compose("system", message)
        )

    def user(self, message=""):
        self.post(
            compose("user", message)
        )

    def assistant(self, message=""):
        self.post(
            compose("assistant", message)
        )

    def complete(self):
        for message in self.completer.complete(self.messages):
            self.post(message)


class ChatTools(Chat):

    def __init__(self, tool_schema, tool_map, client: Client | None = None):
        super().__init__(client)
        self.tool_schema = tool_schema
        self.tool_map = tool_map

    def complete(self):
        for message in self.client.complete_with_tool_calls(
            self.messages,
            self.tool_schema,
            self.tool_map,
        ):
            self.post(message)


def throw(exc):
    raise exc

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
