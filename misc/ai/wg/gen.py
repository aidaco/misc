from dataclasses import dataclass, field
from typing import Protocol, Self, Literal
import copy

from pydantic import BaseModel
import openai
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam


class ToolType[T](Protocol):
    def exec(self) -> T: ...


@dataclass
class Gen:
    messages: list[ChatCompletionMessageParam] = field(default_factory=list)
    tools: list[type[ToolType]] = field(default_factory=list)
    client: openai.OpenAI = field(default_factory=openai.OpenAI)
    model: str = "gpt-4o-2024-08-06"

    def copy(self) -> Self:
        return type(self)(
            messages=copy.deepcopy(self.messages),
            tools=copy.deepcopy(self.tools),
            client=self.client,
        )

    def message(
        self,
        role: Literal["system", "assistant", "user", "tool"],
        content: str,
        **extra,
    ) -> None:
        self.messages.append({"role": role, "content": content, **extra})  # type: ignore

    def system(self, content: str) -> Self:
        self = self.copy()
        self.message("system", content)
        return self

    def assistant(self, content: str) -> Self:
        self = self.copy()
        self.message("assistant", content)
        return self

    def user(self, content: str) -> Self:
        self = self.copy()
        self.message("user", content)
        return self

    def toolcall(self, id: str, content: str) -> None:
        self.message("tool", content, tool_call_id=id)

    def tool(self, tool: type[ToolType]) -> Self:
        self = self.copy()
        self.tools.append(tool)
        return self

    def text(self) -> str:
        args = dict(
            messages=self.messages,
            model=self.model,
            max_tokens=16384,
        )
        if self.tools:
            args["tools"] = [openai.pydantic_function_tool(tool) for tool in self.tools]
        response = self.client.beta.chat.completions.parse(**args)

        print(f"Used {response.usage}")
        msg = response.choices[0].message
        self = self.copy()
        self.messages.append(msg)

        if msg.tool_calls:
            for tool in msg.tool_calls:
                result = tool.function.parsed_arguments.exec()
                self.toolcall(tool.id, result)
            return self.text()

        if msg.refusal:
            raise ValueError(msg.refusal)
        return msg.content

    def gen[T](self, model: type[T]):
        args = dict(
            messages=self.messages,
            model=self.model,
            max_tokens=16384,
            response_format=model,
        )
        if self.tools:
            args["tools"] = [openai.pydantic_function_tool(tool) for tool in self.tools]
        response = self.client.beta.chat.completions.parse(**args)

        # __import__("IPython").embed()
        print(f"Used {response.usage}")
        msg = response.choices[0].message
        self = self.copy()
        self.messages.append(msg)

        if msg.tool_calls:
            for tool in msg.tool_calls:
                result = tool.function.parsed_arguments.exec()  # type: ignore
                self.toolcall(tool.id, result)
            return self.gen(model)

        if msg.parsed:
            return msg.parsed

        raise ValueError(msg.refusal)


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
