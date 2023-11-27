import json

from rich import print

from .clients import OpenAIClient, Client
from .messages import Message


class Chat:
    default_initial_system = "You are a helpful assistant."
    default_client_class = OpenAIClient

    def __init__(
        self,
        client: Client | None = None
    ):
        self.messages = []
        self.client = client if client is not None else self.default_client_class()

    def run(self):
        try:
            self.system(self.default_initial_system)
            while True:
                self.user()
                self.complete()
        except KeyboardInterrupt:
            print("Exit.")

    def post(self, message: Message):
        self.messages.append(message)
        if message.content.text or message.content.image_urls:
            print(message)

    def system(self, message=""):
        self.post(Message.compose("system", message))

    def user(self, message=""):
        self.post(Message.compose("user", message))

    def assistant(self, message=""):
        self.post(Message.compose("assistant", message))

    def complete(self):
        self.post(
            self.client.complete(
                self.messages
            )
        )


class ChatTools(Chat):
    default_tool_schema = []
    default_tool_map = {}

    def __init__(self, client: Client | None = None, tool_schema=None, tool_map=None):
        super().__init__(client)
        self.tool_schema = self.default_tool_schema if tool_schema is None else tool_schema
        self.tool_map = self.default_tool_map if tool_map is None else tool_map

    def complete(self):
        completion, called_tools = self.client.complete_with_tool_calls(
            self.messages,
            self.tool_schema,
            self.tool_map,
        )
        self.post(completion)
        if not called_tools:
            return

        for call in called_tools:
            content = call['content']
            self.post(**call)
        super().complete()


def throw(exc):
    raise exc


if __name__ == '__main__':
    Chat().run()
