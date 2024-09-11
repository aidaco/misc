from dataclasses import dataclass

from rich.console import Console, RenderableType, Group
from rich.panel import Panel
from rich.live import Live
from pydantic import BaseModel
from getch import getch

from wg.gen import Gen


class Object(BaseModel):
    """An inanimate object in the world that players can interact with."""

    name: str


class DetailedObject(Object):
    description: str


class Character(BaseModel):
    """An entity in the world that players can interact with."""

    name: str
    description: str
    goals: str


class Section(BaseModel):
    """"""

    name: str
    description: str


class TreeLocation(BaseModel):
    """An area within the world."""

    name: str
    sublocations: "list[TreeLocation]"


class Exit(BaseModel):
    """A specific way to leave a location."""

    description: str


class GraphLocationLeaf(BaseModel):
    """An area within the world."""

    name: str
    description: str
    exits: list[Exit]

    def asnode(self) -> "GraphLocationNode":
        return GraphLocationNode(
            name=self.name, description=self.description, exits=self.exits
        )


class ConnectedExit(Exit):
    to: "GraphLocationNode"


class GraphLocationNode(BaseModel):
    """An area within the world."""

    name: str
    description: str
    exits: list[Exit | ConnectedExit]


class LocationDetails(BaseModel):
    characters: list[Character]
    objects: list[Object]


class TreeMap(BaseModel):
    """A tree representation of all locations in the game setting.
    All locations in the setting must be represented in the map.
    All locations in the map must be contained in the setting.
    Top-level locations are places such as Mirkwood Forest, Alabama, The Silk Road, The Palace of Versailles, or the Atlantic Ocean.
    Leaf node locations are places such as a house, hallway, bathroom, backyard, or stage and have an empty sublocations field."""

    locations: list[TreeLocation]


def new_root(gen: Gen, world_prompt: str, root_prompt: str) -> GraphLocationNode:
    prompt = f"{world_prompt}\n{root_prompt}"
    return gen.user(prompt).gen(GraphLocationLeaf).asnode()


@dataclass
class LocationDisplay:
    node: GraphLocationNode
    exit_index: int = 0

    def update(self, node: GraphLocationNode) -> None:
        self.node = node
        self.exit_index = 0

    def select_next(self) -> None:
        self.exit_index += 1
        self.exit_index %= len(self.node.exits)

    @property
    def selected(self) -> Exit | ConnectedExit:
        return self.node.exits[self.exit_index]

    def __rich__(self) -> RenderableType:
        desc = Panel(self.node.description)
        exits = [Panel(ex.description) for ex in self.node.exits]
        exits[self.exit_index].border_style = "yellow"
        return Panel(Group(desc, *exits))


def expand_to_exit(
    gen: Gen,
    root: GraphLocationNode,
    node: GraphLocationNode,
    exit: Exit,
    leaf_prompt: str,
) -> GraphLocationNode:
    prompt = f"The current map is: {root}. The current node is: {node.name}. The current exit is: {exit}. {leaf_prompt}"
    leaf = gen.user(prompt).gen(GraphLocationLeaf).asnode()
    ix = node.exits.index(exit)
    node.exits[ix] = ConnectedExit(description=exit.description, to=leaf)
    return leaf


def explore(
    world_prompt: str = "We are creating a detailed game world in the style of the Fallout series set in a post-apocalyptic version of New York City.",
    root_prompt: str = "Generate the starting location.",
    leaf_prompt: str = "Generate the location that is connected to the current node by the current exit.",
    system_prompt: str = "We are creating a detailed game world in the style of the Fallout series set in a post-apocalyptic version of New York City.",
) -> None:
    gen = Gen().system(system_prompt)
    root = new_root(gen, world_prompt, root_prompt)
    current = root
    widget = LocationDisplay(current)
    console = Console()
    live = Live(widget, console=console, refresh_per_second=30, transient=True)
    try:
        with live:
            while True:
                match getch():
                    case "\t":
                        widget.select_next()
                    case " ":
                        current = expand_to_exit(
                            gen, root, current, widget.selected, leaf_prompt
                        )
                        widget.update(current)
                    case "q":
                        break
                live.refresh()
    except KeyboardInterrupt:
        console.print("[red]Stopped.[/]")
