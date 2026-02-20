from pydantic import BaseModel


type WorldName = str
type RegionName = str
type LocationName = str
type MonsterName = str
type MonsterTypeName = str
type RaceName = str
type CharacterClassName = str
type QuestName = str
type CharacterName = str


class Event(BaseModel):
    description: str


class History(BaseModel):
    events: list[Event]


class Region(BaseModel):
    name: RegionName
    description: str
    connected_regions: list["RegionName"]
    locations: list[LocationName]
    history: History


class PlacedItem(BaseModel):
    item: "Item"
    position: "Position"


class Location(BaseModel):
    name: LocationName
    description: str
    region: "RegionName"
    items: list[PlacedItem]
    characters: list[CharacterName]
    monsters: list[MonsterName]
    connected_locations: list[LocationName]
    history: History


class Position(BaseModel):
    region: RegionName
    location: LocationName
    description: str


class Statistic(BaseModel):
    name: str
    value: int


class Feature(BaseModel):
    name: str
    description: str


class Race(BaseModel):
    name: RaceName
    description: str
    features: list[Feature]


class CharacterClass(BaseModel):
    name: CharacterClassName
    description: str
    features: list[Feature]


class Relationship(BaseModel):
    to: str
    description: str


class Item(BaseModel):
    name: str
    type: str
    description: str
    statistics: list[Statistic]
    features: list[Feature]


class Objective(BaseModel):
    description: str
    completed: bool


class Quest(BaseModel):
    name: QuestName
    description: str
    objectives: list[Objective]
    rewards: list[Item]
    completed: bool


class Character(BaseModel):
    name: CharacterName
    race: RaceName
    character_class: CharacterClassName
    position: Position
    statistics: list[Statistic]
    inventory: list[Item]
    quests: list[Quest]
    history: History
    relationships: list[Relationship]


class MonsterType(BaseModel):
    name: MonsterTypeName
    description: str
    statistics: list[Statistic]
    features: list[Feature]


class Monster(BaseModel):
    name: MonsterName
    type: MonsterTypeName
    description: str
    position: Position
    inventory: list[Item]
    relationships: list[Relationship]


class WorldState(BaseModel):
    regions: list[Region]
    locations: list[Location]
    races: list[Race]
    character_classes: list[CharacterClass]
    characters: list[Character]
    monster_types: list[MonsterType]
    monsters: list[Monster]
    history: History


class Action(BaseModel):
    player: CharacterName
    type: str
    description: str
    effects: list[Event]


class GameState(BaseModel):
    players: list[CharacterName]
    turn_index: int
    world: WorldState
    actions: list[Action]
    quests: list[Quest]
