from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Mapping
import json

from pydantic import TypeAdapter
import appdirs
import toml

try:
    import yaml
except ImportError:
    pass


@dataclass
class Config:
    data: Mapping = field(default_factory=dict)
    section_classes: dict[str, type] = field(default_factory=dict)
    section_instances: dict[str, Any] = field(default_factory=dict)

    def parse(self, section_class: type, data: dict):
        return TypeAdapter(section_class).validate_python(data)

    def dump_python(self) -> dict:
        return {
            key: TypeAdapter(section_class).dump_python(
                self.section_instances[key], mode="json"
            )
            for key, section_class in self.section_classes.items()
        }

    def dumps(self, format: Literal["toml", "json", "yaml"] = "toml") -> str:
        value = self.dump_python()
        match format:
            case "toml":
                return toml.dumps(value)
            case "json":
                return json.dumps(value)
            case "yaml":
                return yaml.safe_dump(value)
            case _:
                raise ValueError("Unsupported config format.")

    def section(self, key: str) -> Callable:
        def inner(cls: type):
            self.section_classes[key] = cls
            inst = self.parse(dataclass(cls), self.data.get(key, {}))
            self.section_instances[key] = inst
            return inst

        return inner


def load(data: Mapping) -> None:
    global config
    config = Config(data)


def loads(content: str = "", format: str = "toml") -> None:
    global config
    match format:
        case "toml":
            data = toml.load(content)
        case "json":
            data = json.loads(content)
        case "yaml":
            data = yaml.safe_load(content)
        case _:
            raise ValueError("Unsupported config format.")
    load(data)


def load_path(
    path: Path = Path(appdirs.user_config_dir("wwwmin")) / "config.toml",
) -> None:
    global config
    match path.suffix:
        case _ if not path.exists():
            data = {}
        case ".toml":
            with path.open("r") as fp:
                data = toml.load(fp)
        case ".json":
            with path.open("r") as fp:
                data = json.load(fp)
        case ".yaml":
            with path.open("r") as fp:
                data = yaml.safe_load(fp)
        case _:
            data = {}
    load(data)
