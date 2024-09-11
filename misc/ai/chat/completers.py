from typing import Protocol, Literal, Callable
from dataclasses import dataclass, field
import json

import openai

from .messages import (
    parse,
    construct,
    Messages,
    TextWithToolsChatMessage,
    MultiModalWithToolsChatMessage,
    objectify,
)


@dataclass
class OpenAITextChatCompleter:
    client: openai.OpenAI
    model: Literal["gpt-4-1106-preview"] = "gpt-4-1106-preview"
    tool_schema: list | openai._types.NotGiven = openai._types.NOT_GIVEN
    tool_map: dict | openai._types.NotGiven = openai._types.NOT_GIVEN
    tool_choice: Literal["auto", "none"] | openai._types.NotGiven = (
        openai._types.NOT_GIVEN
    )
    max_tokens: int = 4096

    def provide(
        self,
        role: str,
        messages: Messages[TextWithToolsChatMessage],
    ) -> list[TextWithToolsChatMessage]:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=objectify(messages),
            tools=self.tool_schema,
            tool_choice=self.tool_choice,
            max_tokens=self.max_tokens,
        ).choices[0]
        message = parse(TextWithToolsChatMessage, completion.message)
        match completion.finish_reason:
            case "stop":
                return [message]
            case "tool_calls":
                messages.post(message)
                for call in self._call_tools(message.tool_calls):
                    messages.post(call)
                follow_up = self.provide(role, messages)
                return messages
            case _:
                raise ValueError(f"Unknown finish reason: {completion.finish_reason}")

    def _call_tools(self, tool_calls: list):
        if isinstance(self.tool_map, openai._types.NotGiven):
            raise ValueError("No tools configured.")
        for fncall in tool_calls:
            try:
                name = fncall.function.name
                fn = self.tool_map[name]
                args = json.loads(fncall.function.arguments)
                result = fn(**args)
                yield construct(
                    TextWithToolsChatMessage,
                    tool_call_id=fncall.id,
                    role="tool",
                    name=name,
                    content=result,
                )
            except Exception:
                pass


@dataclass
class OpenAIMultiModalChatCompleter:
    client: openai.OpenAI
    model: Literal["gpt-4-vision-preview"] = "gpt-4-vision-preview"
    tool_schema: list | openai._types.NotGiven = openai._types.NOT_GIVEN
    tool_map: dict | openai._types.NotGiven = openai._types.NOT_GIVEN
    tool_choice: Literal["auto", "none"] | openai._types.NotGiven = (
        openai._types.NOT_GIVEN
    )
    max_tokens: int = 4096

    def provide(
        self,
        role: str,
        messages: Messages[MultiModalWithToolsChatMessage],
    ) -> list[MultiModalWithToolsChatMessage]:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=objectify(messages),
            tools=self.tool_schema,
            tool_choice=self.tool_choice,
            max_tokens=self.max_tokens,
        ).choices[0]
        message = parse(MultiModalWithToolsChatMessage, completion.message)
        match completion.finish_reason:
            case "stop":
                return [message]
            case "tool_calls":
                tool_calls = list(self._call_tools(message.tool_calls, tool_map))
                follow_up = self.complete_with_tool_calls(
                    messages + tool_calls, tool_schema, tool_map, tool_choice
                )
                return [message, *tool_calls, *follow_up]
            case _:
                raise ValueError(f"Unknown finish reason: {completion.finish_reason}")

    def _call_tools(self, tool_calls: list, tool_map: dict[str, Callable]):
        for fncall in tool_calls:
            try:
                name = fncall.function.name
                fn = tool_map[name]
                args = json.loads(fncall.function.arguments)
                result = fn(**args)
                yield construct(
                    tool_call_id=fncall.id,
                    role="tool",
                    name=name,
                    content=result,
                )
            except Exception:
                pass
