from typing import Literal, runtime_checkable, Protocol, Callable
from dataclasses import dataclass

from rich import print
from rich.console import Group
from rich.panel import Panel
from pydantic import TypeAdapter


STYLES = {
    "system": "bright_blue italic on black",
    "user": "bright_red on black",
    "assistant": "bright_green on black",
    "border": "bright_black bold not italic on black",
    "editor_border": "bright_yellow on black",
}


@runtime_checkable
class Objectable(Protocol):
    def object(self) -> dict: ...


def objectify(inst):
    match inst:
        case Objectable():
            return inst.object()
        case [*parts]:
            return [objectify(o) for o in parts]
        case _:
            return inst


@dataclass
class TextContentPart:
    text: str

    def object(self):
        return {"type": "text", "text": self.text}

    def __rich__(self):
        return self.text


@dataclass
class ImageContentPart:
    url: str

    def object(self):
        return {"type": "image_url", "image_url": {"url": self.url}}

    def __rich__(self):
        return f"[link={self.url}]{self.url}[/link]"


type TextContent = str
type MultiModalContent = list[TextContentPart | ImageContentPart]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    def object(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass
class ChatMessage[RoleType: str, ContentType: (TextContent, MultiModalContent)]:
    role: RoleType
    content: ContentType

    def object(self):
        return {"role": self.role, "content": objectify(self.content)}

    def __rich__(self):
        match self.content:
            case str(text):
                content = text
            case [*parts]:
                content = Group(*parts)
        return Panel.fit(
            content,
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES["border"],
        )


@dataclass
class ChatMessageToolCall[RoleType: str, ContentType: (TextContent, MultiModalContent)]:
    content: ContentType
    tool_calls: list[ToolCall]
    role: RoleType
    function_call: None = None

    def object(self):
        obj = {
            "role": self.role,
            "content": objectify(self.content),
        }
        if not self.tool_calls:
            return obj
        return obj | {"tool_calls": [call.json() for call in self.tool_calls]}

    def __rich__(self):
        match self.content:
            case str(text):
                content = text
            case [*parts]:
                content = Group(*parts)
        content = content if not self.tool_calls else Group(content, self.tool_calls)
        return Panel.fit(
            content,
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES["border"],
        )


@dataclass
class ChatMessageToolResult[
    RoleType: str,
    ContentType: (TextContent, MultiModalContent),
]:
    content: ContentType
    tool_call_id: str
    name: str
    role: RoleType

    def object(self):
        return {
            "role": self.role,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": objecctify(self.content),
        }

    def __rich__(self):
        match self.content:
            case str(text):
                content = text
            case [*parts]:
                content = Group(*parts)
        return Panel.fit(
            Group(self.tool_call_id, self.name, content),
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES["border"],
        )


type TextWithToolsChatMessage = (
    ChatMessage[Literal["system", "user", "assistant"], TextContent]
    | ChatMessageToolCall[Literal["assistant"], TextContent]
    | ChatMessageToolResult[Literal["tool"], TextContent]
)
type MultiModalWithToolsChatMessage = (
    ChatMessage[Literal["system", "user", "assistant"], MultiModalContent]
    | ChatMessageToolCall[Literal["assistant"], MultiModalContent]
    | ChatMessageToolResult[Literal["tool"], MultiModalContent]
)


class MessageProvider[MessageType](Protocol):
    def provide(self, role: str, messages: list[MessageType]) -> list[MessageType]: ...


@dataclass
class Messages[MessageType]:
    messages: list[MessageType]
    watchers: list[Callable]

    def object(self):
        return [objectify(msg) for msg in self.messages]

    def notify(self, fn: Callable[[MessageType], None]):
        self.watchers.append(fn)

    def post(self, message: MessageType):
        self.messages.append(message)
        for fn in self.watchers:
            fn(message)
        match message.content:
            case "":
                return
            case None:
                return
            case _:
                print(message)


def parse(cls, obj):
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return TypeAdapter(cls, config={"extra": "forbid"}).validate_python(obj)


def construct(cls, **properties):
    return parse(cls, properties)
