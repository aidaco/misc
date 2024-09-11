from dataclasses import dataclass, field
from typing import Any, Protocol, Self, Literal
import copy

from pydantic import BaseModel
import openai
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam


class ToolType[T](Protocol):
    def exec(self) -> T: ...


@dataclass
class Prompt:
    messages: list[ChatCompletionMessageParam] = field(default_factory=list)
    tools: list[type[ToolType]] = field(default_factory=list)
    client: openai.OpenAI = field(default_factory=openai.OpenAI)
    model: str = "gpt-4o-2024-08-06"
    max_tokens: int = 16384
    response_format: type[BaseModel] | None = None

    @property
    def last(self) -> ChatCompletionMessageParam:
        return self.messages[-1]

    def copy(self) -> Self:
        return type(self)(
            messages=copy.deepcopy(self.messages),
            tools=copy.deepcopy(self.tools),
            client=self.client,
            model=self.model,
        )

    def message(
        self,
        role: Literal["system", "assistant", "user", "tool"],
        content: str,
        **extra,
    ) -> None:
        self.messages.append({"role": role, "content": content, **extra})  # type: ignore

    def complete(self) -> None:
        args = dict(
            messages=self.messages,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        if self.response_format is not None:
            args["response_format"] = self.response_format
        if self.tools:
            args["tools"] = [openai.pydantic_function_tool(tool) for tool in self.tools]
        response = self.client.beta.chat.completions.parse(**args)

        print(f"Used {response.usage}")
        msg = response.choices[0].message
        if msg.refusal:
            raise ValueError(msg.refusal)
        self.messages.append(msg)

    def should_call_tools(self) -> bool:
        match self.messages:
            case [*_, {"role": "assistant", "tool_calls": tool_calls}] if tool_calls:
                return True
            case _:
                return False

    def call_tools(self) -> None:
        for tool in self.last.tool_calls:  # type: ignore
            result = tool.function.parsed_arguments.exec()
            self.message("tool", result, tool_call_id=tool.id)

    def complete_with_tools(self) -> None:
        while True:
            self.complete()
            if self.should_call_tools():
                self.call_tools()
            else:
                break


@dataclass
class Chat:
    prompt: Prompt = field(default_factory=Prompt)
    inplace: bool = True

    def tool(self, tool: type[ToolType]) -> Self:
        self = self.copy()
        self.prompt.tools.append(tool)
        return self

    def system(self, content: str) -> Self:
        self = self.copy()
        self.prompt.message("system", content)
        return self

    def assistant(self, content: str) -> Self:
        self = self.copy()
        self.prompt.message("assistant", content)
        return self

    def user(self, content: str) -> Self:
        self = self.copy()
        self.prompt.message("user", content)
        return self

    def text(self) -> str:
        if self.prompt.response_format:
            self = self.copy()
            self.prompt.response_format = None
        self.prompt.complete_with_tools()
        return self.prompt.last.content

    def model[T](self, model: type[T]) -> T:
        if self.prompt.response_format is not model:
            self = self.copy()
            self.prompt.response_format = model
        self.prompt.complete_with_tools()
        return self.prompt.last.parsed

    def copy(self) -> Self:
        if self.inplace:
            return self
        return type(self)(prompt=self.prompt.copy())


class EvalPython(BaseModel):
    """Evaluate a single python expression in an empty global and local scope and return the JSON serialized result."""

    src: str

    def exec(self):
        return eval(self.src, {}, {})


class ExecPython(BaseModel):
    """Execute python source code in an empty global and local scope and return the JSON serialized globals dictionary."""

    src: str

    def exec(self):
        return exec(self.src, {}, {})
