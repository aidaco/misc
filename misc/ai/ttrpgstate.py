from pydantic import BaseModel
from openai import OpenAI


type CharacterName = str
type RaceName = str
type CharacterClassName = str
type QuestName = str


class Event(BaseModel):
    description: str


class Action(BaseModel):
    type: str
    description: str
    effects: list[Event]


class Statistic(BaseModel):
    name: str
    value: int


class Feature(BaseModel):
    name: str
    description: str


class Item(BaseModel):
    name: str
    type: str
    description: str
    statistics: list[Statistic]
    features: list[Feature]


class Race(BaseModel):
    name: RaceName
    description: str
    features: list[Feature]


class CharacterClass(BaseModel):
    name: CharacterClassName
    description: str
    features: list[Feature]


class Relationship(BaseModel):
    to: CharacterName
    description: str


class Position(BaseModel):
    region: "Region"
    location: "Location"
    description: str


class Character(BaseModel):
    name: CharacterName
    race: RaceName
    character_class: CharacterClassName
    statistics: list[Statistic]
    position: Position
    inventory: list[Item]
    quests: list["Quest"]
    history: list[Event]
    relationships: list[Relationship]


class Objective(BaseModel):
    description: str
    completed: bool


class Quest(BaseModel):
    name: QuestName
    description: str
    objectives: list[Objective]
    rewards: list[Item]
    completed: bool


type LocationName = str


class Location(BaseModel):
    name: LocationName
    description: str
    region: "RegionName"
    characters: list[CharacterName]
    connected_locations: list[LocationName]
    history: list[Event]


type RegionName = str


class Region(BaseModel):
    name: RegionName
    description: str
    locations: list[LocationName]
    connected_regions: list["RegionName"]
    history: list[Event]


class WorldState(BaseModel):
    races: list[Race]
    classes: list[CharacterClass]
    locations: list[Location]
    regions: list[Region]
    players: list[Character]
    quests: list[Quest]
    history: list[Event]


client = OpenAI()


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
    region_prompt = f"{prompt}\n\nGenerate a region for this world."
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

    num_regions = 5
    for _ in range(num_regions):
        region = generate_instance(region_prompt, Region)
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
