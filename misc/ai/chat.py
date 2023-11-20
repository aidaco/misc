import json

from rich import print
from rich.panel import Panel
import openai
from twidge.widgets import Close, EditString, Framed


key = open("/home/aidan/.secrets/openai-api-key").read().strip()
client = openai.OpenAI(api_key=key)


class Chat:
    styles = {
        "system": "bright_blue italic on black",
        "user": "bright_red on black",
        "assistant": "bright_green on black",
        "border": "bright_black bold not italic on black",
        "editor_border": "bright_yellow on black",
    }
    default_initial_system = "You are a helpful assistant."

    def __init__(self):
        self.messages = []

    def run(self):
        try:
            self.system(self.default_initial_system)
            while True:
                self.user()
                self.complete()
        except KeyboardInterrupt:
            print("Exit.")

    def show_message(self, message):
        content = _get_item_or_attr(message, "content", None)
        role = _get_item_or_attr(message, "role", None)
        if not role or not content:
            return

        match content:
            case str():
                out = content
            case [*parts]:
                texts = []
                images = []
                for p in parts:
                    match p:
                        case {'type': 'text', 'text': text}:
                            texts.append(text)
                        case {'type': 'image_url', 'image_url': {'url': url}}:
                            images.append(url)
                text = '\n'.join(texts)
                images = ' '.join(f'[link={url}]Image {i}[/]' for i, url in enumerate(images))
                out = f'{text}\n{images}'
        print(
            Panel.fit(
                out,
                title=role,
                title_align="left",
                style=self.styles[role],
                border_style=self.styles['border'],
            )
        )

    def post(self, message=None, **properties):
        msg = (
            message
            or properties
            or throw(ValueError("Must pass message or properties."))
        )
        self.messages.append(msg)
        self.show_message(msg)

    def editprompt(self, role, message):
        widget = Close(
            Framed(
                EditString(
                    message, text_style=self.styles[role], cursor_line_style=self.styles[role]
                ),
                title=role,
                title_align="left",
                style=self.styles['editor_border'],
            )
        )
        text = widget.run()
        urls, no_urls = extract_matches(URL_REGEX, text)
        paths, cleaned = extract_matches(PATH_REGEX, no_urls)
        if urls or paths:
            return {
                "role": role,
                "content": [
                    {"type": "text", "text": cleaned},
                    *({"type": "image_url", "image_url": {"url": url}} for url in urls),
                    *(
                        {
                            "type": "image_url",
                            "image_url": {"url": base64url(path.open("rb"))},
                        }
                        for path in paths
                    ),
                ],
            }
        return {"role": role, "content": text}

    def system(self, message=""):
        self.post(self.editprompt("system", message))

    def user(self, message=""):
        self.post(self.editprompt("user", message))

    def assistant(self, message=""):
        self.post(self.editprompt("assistant", message))

    def complete(self):
        completion = (
            client.chat.completions.create(
                model="gpt-4-vision-preview",
                messages=self.messages,
                max_tokens=4096,
            )
            .choices[0]
            .message
        )
        self.post(completion)


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


if __name__ == "__main__":
    Chat().run()

