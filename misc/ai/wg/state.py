from contextlib import contextmanager
import sys
from typing import Iterator, Literal, Self

from pydantic import BaseModel

from wg.gen import Gen


class Location(BaseModel):
    name: str
    description: str
    state: str


class Character(BaseModel):
    name: str
    description: str
    state: str


class Goal(BaseModel):
    name: str
    description: str
    state: str


class UpdateBase(BaseModel):
    @classmethod
    @contextmanager
    def use_state(cls, state: "State") -> Iterator[None]:
        try:
            cls.GAME_STATE: State = state
            yield
        finally:
            try:
                del cls.GAME_STATE
            except NameError:
                pass


class QuestUpdate(UpdateBase):
    type: Literal["quest"]
    name: str
    description: str
    state: str

    def exec(self) -> Self:
        state: State = self.GAME_STATE
        for q in state.quest:
            if q.name == self.name:
                q.state = self.state
        else:
            state.quest.append(Goal(self.name, self.description, self.state))
        return self


class LocationUpdate(UpdateBase):
    type: Literal["location"]
    name: str
    description: str
    state: str

    def exec(self) -> Self:
        state: State = self.GAME_STATE
        for loc in state.locations:
            if loc.name == self.name:
                loc.state = self.state
        else:
            state.locations.append(Location(self.name, self.description, self.state))
        return self


class CharacterUpdate(UpdateBase):
    type: Literal["character"]
    name: str
    description: str
    state: str

    def exec(self) -> Self:
        state: State = self.GAME_STATE
        for ch in state.characters:
            if ch.name == self.name:
                ch.state = self.state
        else:
            state.characters.append(Character(self.name, self.description, self.state))
        return self


class State(BaseModel):
    setting: str
    quest: list[Goal]
    locations: list[Location]
    characters: list[Character]


def stateful(
    prompt: str = "We are creating a detailed haunted mansion murder mystery game set in the style of the Fallout series set in a post-apocalyptic version of the Hamptons.",
):
    gen = Gen().system(
        "You are the dungeon master of a TTRPG-like text-based adventure game."
    )
    game = gen.user(
        f"{prompt}\nGenerate a high-level description of the setting & plot."
    ).gen(State)

    history = []

    try:
        while True:
            prompt = gen.user(
                f"The conversation history is {history}.\n"
                f"The game state is {game}.\n"
                "Prompt the user for an open-ended action."
            ).text()
            print(prompt)
            action = input(">")
            match action:
                case "quit":
                    sys.exit(0)
                case "debug":
                    __import__("IPython").embed()

            with UpdateBase.use_state(game):
                results = (
                    gen.user(
                        f"The conversation history is {history}.\n"
                        f"The game state is {game}.\n"
                        f"The user's action is '{action}'.\n"
                        "Before proceeding, use the provided tools to update the game state to reflect the results of this action."
                        "Then describe the action & results in detail to the user."
                    )
                    .tool(QuestUpdate)
                    .tool(LocationUpdate)
                    .tool(CharacterUpdate)
                    .text()
                )
            print(results)
            history.append((prompt, action, results))
    except KeyboardInterrupt:
        pass
