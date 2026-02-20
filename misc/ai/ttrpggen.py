from dataclasses import dataclass, field
from typing import Self

from rich import get_console
from pydantic import BaseModel
from openai import OpenAI

from misc.ai.ttrpgstate import (
    RegionName,
    LocationName,
    MonsterName,
    MonsterTypeName,
    RaceName,
    CharacterClassName,
    CharacterName,
    WorldState,
)


client = OpenAI()


class Subject(BaseModel):
    name: str
    description: str


class TTRPGInfo(BaseModel):
    world: Subject
    campaign: Subject
    quest: Subject

    @classmethod
    def gen(cls, prompt: str) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            "Provide or generate more information about the TTRPG that the user would like to play. Descriptions should be 3-5 sentences.",
            cls,
        )


class RegionInfo(BaseModel):
    regions: list[Subject]

    @classmethod
    def gen(cls, prompt: str, ttrpg_info: TTRPGInfo) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this information: '{ttrpg_info.model_dump_json()}'.\n\n"
            "List all of the regions that exist in this TTRPG game world. Descriptions should be 1-2 sentences.",
            cls,
        )


class MonsterTypeInfo(BaseModel):
    monster_types: list[Subject]

    @classmethod
    def gen(cls, prompt: str, ttrpg_info: TTRPGInfo) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this information: '{ttrpg_info.model_dump_json()}'.\n\n"
            "List all of the type of monsters that exist in this game world. "
            "Descriptions should be 1-2 sentences.",
            cls,
        )


class RaceInfo(BaseModel):
    races: list[Subject]

    @classmethod
    def gen(cls, prompt: str, ttrpg_info: TTRPGInfo) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this information: '{ttrpg_info.model_dump_json()}'.\n\n"
            "List all of the races of beings that exist in this world. Descriptions should be 1-2 sentences.",
            cls,
        )


class CharacterClassInfo(BaseModel):
    character_classes: list[Subject]

    @classmethod
    def gen(cls, prompt: str, ttrpg_info: TTRPGInfo) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this information: '{ttrpg_info.model_dump_json()}'.\n\n"
            "List all of the character classes that players or NPCs can have in this world. Descriptions should be 1-2 sentences.",
            cls,
        )


class CharacterInfo(BaseModel):
    name: CharacterName
    description: str
    race: RaceName
    character_class: CharacterClassName

    @classmethod
    def gen_player(
        cls,
        prompt: str,
        ttrpg_info: TTRPGInfo,
        race_info: RaceInfo,
        character_class_info: CharacterClassInfo,
    ) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this background information: '{ttrpg_info.model_dump_json()}'.\n\n"
            f"We have generated this race information: '{race_info.model_dump_json()}'.\n\n"
            f"We have generated this character class information: '{character_class_info.model_dump_json()}'.\n\n"
            "Generate a player character suitable for this TTRPG world. Descriptions should be 3-4 sentences.",
            cls,
        )

    @classmethod
    def gen_nonplayer(
        cls,
        prompt: str,
        ttrpg_info: TTRPGInfo,
        race_info: RaceInfo,
        character_class_info: CharacterClassInfo,
    ) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this background information: '{ttrpg_info.model_dump_json()}'.\n\n"
            f"We have generated this race information: '{race_info.model_dump_json()}'.\n\n"
            f"We have generated this character class information: '{character_class_info.model_dump_json()}'.\n\n"
            "Generate a non-player character suitable for this TTRPG world. Descriptions should be 2-3 sentences.",
            cls,
        )


def generate_info(
    prompt: str,
) -> tuple[TTRPGInfo, RegionInfo, MonsterTypeInfo, RaceInfo, CharacterClassInfo]:
    ttrpg_info = TTRPGInfo.gen(prompt)
    race_info = RaceInfo.gen(prompt, ttrpg_info)
    character_classes_info = CharacterClassInfo.gen(prompt, ttrpg_info)
    region_info = RegionInfo.gen(prompt, ttrpg_info)
    monster_types_info = MonsterTypeInfo.gen(prompt, ttrpg_info)

    return (
        ttrpg_info,
        region_info,
        monster_types_info,
        race_info,
        character_classes_info,
    )


class ItemBase(BaseModel):
    name: str


class CharacterBase(BaseModel):
    name: CharacterName
    character_class: CharacterClassName
    inventory: list[ItemBase]


class MonsterTypeBase(BaseModel):
    name: MonsterTypeName


class MonsterBase(BaseModel):
    name: MonsterName
    type: MonsterTypeName


class LocationBase(BaseModel):
    name: LocationName
    monsters: list[MonsterBase]
    characters: list[CharacterBase]


class RegionBase(BaseModel):
    name: RegionName
    description: str
    locations: list[LocationBase]


class WorldStateBase(BaseModel):
    regions: list[RegionBase]


def generate_instance[T](prompt: str, model: type[T]) -> T:
    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=8192,
        response_format=model,
    )

    response = completion.choices[0].message

    if response.refusal:
        raise ValueError(f"Refused to generate with message: {response.refusal}")

    result = response.parsed

    if result is None:
        raise ValueError("Failed to generate instance")

    return result


def generate_text(prompt: str) -> str:
    completion = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    response = completion.choices[0].message
    if response.refusal:
        raise ValueError(f"Refused to generate with message: {response.refusal}")

    result = response.content

    if result is None:
        raise ValueError("Failed to generate text")

    return result


def generate_world_part[T](
    world_prompt: str, model_prompt: str, model: type[T], n: int = 5
) -> list[T]:
    full_prompt = f"{world_prompt}\n\n{model_prompt}"
    return [generate_instance(full_prompt, model) for _ in range(n)]


def generate_worldstate(prompt: str) -> WorldState:
    # Generate the regions of the world
    races: list[Race] = generate_world_part(
        prompt, "Generate a race of beings that exists in this world.", Race
    )
    classes: list[CharacterClass] = generate_world_part(
        prompt,
        "Generate a character class that makes sense in this world.",
        CharacterClass,
    )

    regions: list[Region] = generate_world_part(
        prompt, "Generate a region that exists in this world.", Region
    )
    locations: list[Location] = generate_world_part(
        prompt, "Generate a location that exists in this world.", Location
    )
    characters: list[Character] = generate_world_part(
        prompt, "Generate a character that exists in this world.", Character
    )
    players: list[Character] = generate_world_part(
        prompt, "Generate a character to be controlled by a player.", Character
    )

    quests: list[Quest]
    history: list[Event]

    class RegionBase(BaseModel):
        name: RegionName
        description: str

    regions: list[Region] = []
    locations: list[Location] = []
    num_regions = 5
    for _ in range(num_regions):
        region = generate_world_part(region_prompt, Region)
        regions.append(region)

        # Generate locations within each region
        location_prompt = f"Generate some locations for the region '{region.name}'."
        num_locations = 5
        region.locations = []
        for _ in range(num_locations):
            location = generate_instance(location_prompt, Location)

            # Generate characters within each location
            character_prompt = f"Describe a character that might be found in the location '{location.name}' in the region '{region.name}'."
            num_characters = 5

            for _ in range(num_characters):
                character = generate_instance(character_prompt, Character)
                characters.append(character)
                location.characters.append(character.name)

            region.locations.append(location.name)
            locations.append(location)

        # Optionally generate events and connect locations
        event_prompt = (
            f"Describe an event that has occurred in the region '{region.name}'."
        )
        num_events = int(
            generate_text(
                f"{event_prompt}\n\nHow many events should be noted in the region '{region.name}'?"
            )
        )
        for _ in range(num_events):
            event = generate_instance(event_prompt, Event)
            region.history.append(event)

    worldstate.regions = regions

    # Optionally generate quests
    quest_prompt = "Generate a major quest for this world."
    num_quests = int(
        generate_text(
            f"{quest_prompt}\n\nHow many major quests should there be in this world?"
        )
    )
    for _ in range(num_quests):
        quest = generate_instance(quest_prompt, Quest)
        worldstate.quests.append(quest)

    # Optionally generate global events for the world
    world_event_prompt = (
        "Generate a significant event that has impacted the entire world."
    )
    num_world_events = int(
        generate_text(
            f"{world_event_prompt}\n\nHow many significant events should there be in this world?"
        )
    )
    for _ in range(num_world_events):
        world_event = generate_instance(world_event_prompt, Event)
        worldstate.history.append(world_event)

    return worldstate


class SimpleItem(BaseModel):
    name: str
    description: str


class SimpleCharacter(BaseModel):
    name: str
    description: str
    inventory: list[SimpleItem]


class SimpleAdjoining(BaseModel):
    connected_by: str
    compass_direction: str
    location: "SimpleLocation"


class SimpleLocation(BaseModel):
    description: str
    connected_to: list[SimpleAdjoining]


class SimpleEvent(BaseModel):
    description: str
    effects: list[str]


class SimpleInitialState(BaseModel):
    players: list[SimpleCharacter]
    inciting_incidents: list[SimpleEvent]
    current_location: SimpleLocation

    @classmethod
    def gen(cls, prompt: str, ttrpg_info: TTRPGInfo) -> Self:
        return generate_instance(
            f"The user has provided this prompt: '{prompt}'.\n\n"
            f"We have generated this information: '{ttrpg_info.model_dump_json()}'.\n\n"
            "Provide the initial state of the TTRPG game. Descriptions should be 2-3 sentences.",
            cls,
        )


class SimpleActionResults(BaseModel):
    events: list[SimpleEvent]
    is_turn_over: bool


console = get_console()
print = console.print
input = console.input


@dataclass
class SimpleGame:
    info: TTRPGInfo
    players: list[SimpleCharacter]
    location: SimpleLocation
    events: list[SimpleEvent]
    turn_index: int = 0

    @classmethod
    def new(cls, prompt: str) -> Self:
        info = TTRPGInfo.gen(prompt)
        initial = SimpleInitialState.gen(prompt, info)
        return cls(
            info, initial.players, initial.current_location, initial.inciting_incidents
        )

    def gen_initial_prompt(self) -> str:
        return generate_text(
            f"We are playing this TTRPG: '{self.info.model_dump_json()}'.\n\n"
            f"These are the player characters: '[{",".join(p.model_dump_json() for p in self.players)}]'.\n\n"
            f"This party is currently in this location: '{self.location.model_dump_json()}'.\n\n"
            f"These are the recent events: '[{",".join(e.model_dump_json() for e in self.events)}]'.\n\n"
            "Provide a 3-10 sentence narrative introduction providing background information on the game world and recent events leading to the current situation.",
        )

    def gen_action_prompt(self, last_description) -> str:
        return generate_text(
            f"We are playing this TTRPG: '{self.info.model_dump_json()}'.\n\n"
            f"These are the player characters: '[{",".join(p.model_dump_json() for p in self.players)}]'.\n\n"
            f"This party is currently in this location: '{self.location.model_dump_json()}'.\n\n"
            f"These are the recent events: '[{",".join(e.model_dump_json() for e in self.events)}]'.\n\n"
            f"Don't be repetitive, the last thing we told the players was: '{last_description}'.\n\n"
            f"It is currently {self.players[self.turn_index].name}'s turn.\n\n"
            "Provide a brief 1-3 sentence prompt that will be given to the user to request their next action. The prompt should end with 'what do you do?' or similar.",
        )

    def gen_action_results(self, action: str) -> SimpleActionResults:
        return generate_instance(
            f"We are playing this TTRPG: '{self.info.model_dump_json()}'.\n\n"
            f"These are the player characters: '[{",".join(p.model_dump_json() for p in self.players)}]'.\n\n"
            f"This party is currently in this location: '{self.location.model_dump_json()}'.\n\n"
            f"These are the recent events: '[{",".join(e.model_dump_json() for e in self.events)}]'.\n\n"
            f"It is currently {self.players[self.turn_index].name}'s turn.\n\n"
            f"The player has taken this action: '{action}'.\n\n"
            "Provide the immediate results of this particular action. "
            "When it makes sense try to stop the players by including one or more new, open-ended obstacles in their way. ",
            SimpleActionResults,
        )

    def gen_action_description(
        self, last_description: str, action: str, results: SimpleActionResults
    ) -> str:
        return generate_text(
            f"We are playing this TTRPG: '{self.info.model_dump_json()}'.\n\n"
            f"These are the player characters: '[{",".join(p.model_dump_json() for p in self.players)}]'.\n\n"
            f"This party is currently in this location: '{self.location.model_dump_json()}'.\n\n"
            f"These are the recent events: '[{",".join(e.model_dump_json() for e in self.events)}]'.\n\n"
            f"Don't be repetitive, the last thing we told the players was: '{last_description}'.\n\n"
            f"It is currently {self.players[self.turn_index].name}'s turn.\n\n"
            f"The player has taken this action: '{action}'.\n\n"
            f"The results of this action are: '{results.model_dump_json()}'.\n\n"
            f"Provide a 1-3 sentence narrative description of the results of this action.",
        )

    def play(self) -> None:
        last_description = self.gen_initial_prompt()
        print(f"[cyan]{last_description}[/]")
        while True:
            last_description = self.turn(last_description)
            self.turn_index += 1
            self.turn_index %= len(self.players)

    def turn(self, last_description: str) -> str:
        while True:
            prompt = self.gen_action_prompt(last_description)
            print(f"[green]{prompt}[/]")
            action = input(f"[yellow]{self.players[self.turn_index].name}[/]>")
            results = self.gen_action_results(action)
            description = self.gen_action_description(prompt, action, results)
            print(f"[red]{description}[/]")
            self.events.extend(results.events)
            if results.is_turn_over:
                return description
