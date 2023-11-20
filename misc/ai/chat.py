import json

from rich import print
from rich.panel import Panel
import openai

from .completers import OpenAICompleter
from .messages import Message


class Chat:
    default_initial_system = "You are a helpful assistant."

    def __init__(self, completer=None):
        self.messages = []
        self.completer = completer if completer is not None else OpenAICompleter()

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
            self.completer.complete(
                self.messages
            )
        )


def execute_python(source):
    print(source)
    if input("Execute?") == "y":
        env = dict()
        exec(source, env, env)


class ChatTools(Chat):
    default_tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_python",
                "description": "Execute Python source code. Prompts the user for confirmation before execution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "The Python source code to be executed.",
                        },
                    },
                    "required": ["source"],
                },
            },
        }
    ]
    default_functions = {
        "execute_python": execute_python,
    }

    def __init__(self, tools=None, functions=None):
        self.messages = []
        self.tools = self.default_tools if tools is None else tools
        self.functions = self.default_functions if functions is None else functions

    def complete(self):
        completion = (
            client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=self.messages,
                tools=self.default_tools,
                tool_choice="auto",
            )
            .choices[0]
            .message
        )
        self.post(completion)
        tool_calls = getattr(completion, "tool_calls", None)
        if not tool_calls:
            return
        for fncall in tool_calls:
            fn = self.default_functions[fncall.function.name]
            args = json.loads(fncall.function.arguments)
            self.post(
                tool_call_id=fncall.id,
                role="tool",
                name=fncall.function.name,
                content=fn(**args),
            )
        follow_up = (
            client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=self.messages,
            )
            .choices[0]
            .message
        )
        self.post(follow_up)


def throw(exc):
    raise exc
