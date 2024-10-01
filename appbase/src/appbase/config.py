from dataclasses import dataclass, field
import io
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    Literal,
    Mapping,
    Self,
    Protocol,
    TextIO,
    TypeAlias,
)
import json
import typing

from pydantic import BaseModel, TypeAdapter
import appdirs
import toml
import yaml


type Format = Literal["toml", "json", "yaml", "unsafe_yaml"]
FORMATS: set[str] = {"toml", "json", "yaml", "safe_yaml"}
Model: TypeAlias = BaseModel


class ConfigConfigType[C: "Config"](Protocol):
    __init__: Callable

    def load(self) -> C: ...
    def dump(self, config: C) -> None: ...
    def dumps(self, config: C) -> str: ...


def dump_str(value: Any, format: Format) -> str:
    match format:
        case "toml":
            return toml.dumps(value)
        case "json":
            return json.dumps(value)
        case "yaml":
            return yaml.dump(value)
        case "safe_yaml":
            return yaml.safe_dump(value)
    raise ValueError("Unsupported format.")


def write_format(value: Any, file: TextIO | BinaryIO, format: Format) -> None:
    match format:
        case "toml":
            match file:
                case io.TextIOBase():
                    toml.dump(value, file)
                case io.BufferedIOBase():
                    buffer = io.StringIO()
                    toml.dump(value, buffer)
                    file.write(buffer.getvalue().encode())
        case "json":
            match file:
                case TextIO():
                    json.dump(value, file)
                case BinaryIO():
                    buffer = io.StringIO()
                    json.dump(value, buffer)
                    file.write(buffer.getvalue().encode())
        case "safe_yaml":
            yaml.dump(value, file)
        case "yaml":
            yaml.dump(value, file)
    raise ValueError("Unsupported format.")


def read_format(file: TextIO | BinaryIO, format: Format) -> dict:
    match format:
        case "toml":
            match file:
                case io.TextIOBase():
                    return toml.load(file)
                case io.BufferedIOBase():
                    return toml.loads(file.read().decode())
        case "json":
            return json.load(file)
        case "safe_yaml":
            return yaml.safe_load(file)
        case "yaml":
            return yaml.unsafe_load(file)
    raise ValueError("Unsupported format.")


type TypeAdapterMappingType[M] = dict[type[M], TypeAdapter[M]]
TYPEADAPTER_CACHE: TypeAdapterMappingType = {}


def parse_python[M](
    obj: Any,
    model: type[M],
    typeadapter_cache: dict[type[M], TypeAdapter[M]] = TYPEADAPTER_CACHE,
) -> M:
    try:
        adapter = typeadapter_cache[model]
    except KeyError:
        adapter = typeadapter_cache[model] = TypeAdapter(model)
    return adapter.validate_python(obj)


def dump_python[M](
    obj: M, typeadapter_cache: dict[type[M], TypeAdapter[M]] = TYPEADAPTER_CACHE
) -> dict:
    model = type(obj)
    try:
        return typeadapter_cache[model].dump_python(obj, mode="json")
    except KeyError:
        typeadapter_cache[model] = adapter = TypeAdapter(model)
        return adapter.dump_python(obj, mode="json")


@dataclass
class AppdirConfigConfig:
    name: str
    override_data: dict | None = None
    override_path: Path | None = None
    override_datadir: Path | None = None
    override_configdir: Path | None = None

    @property
    def configpath(self) -> Path:
        return self.override_path or self.configdir / "config.toml"

    @property
    def datadir(self) -> Path:
        return self.override_datadir or Path(appdirs.user_data_dir(self.name)).resolve()

    @property
    def configdir(self) -> Path:
        return (
            self.override_configdir
            or Path(appdirs.user_config_dir(self.name)).resolve()
        )

    def load(self, format: Format | None = None, path: Path | None = None) -> "Config":
        return Config(self, self._load(format, path))

    def _load(self, format: Format | None = None, path: Path | None = None) -> dict:
        if self.override_data:
            return self.override_data
        path = path or self.configpath
        if not path.exists():
            return {}
        elif path.is_dir():
            raise ValueError(f"Expected a file not a directory: {path}")
        format = typing.cast(Format, format or path.suffix.lstrip("."))
        assert format in FORMATS
        with self.configpath.open("rb") as file:
            return read_format(file, format)

    def dump(
        self, config: "Config", format: Format | None = None, path: Path | None = None
    ) -> None:
        path = path or self.configpath
        if format is None:
            format = typing.cast(Format, path.suffix.lstrip("."))
            assert format in FORMATS
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.configpath.open("wb") as file:
            write_format(config.dump_all(), file, format)

    def dumps(self, config: "Config", format: Format = "toml") -> str:
        return dump_str(config.dump_all(), format)


@dataclass
class Config[CC: ConfigConfigType]:
    config: CC
    data: Mapping = field(default_factory=dict)
    section_classes: dict[str, type] = field(default_factory=dict)
    section_instances: dict[str, Any] = field(default_factory=dict)

    def load(self, key: str) -> Any:
        return parse_python(self.data[key], self.section_classes[key])

    def dump(self, key: str) -> dict:
        return dump_python(self.data[key])

    def dump_all(self) -> dict[str, dict]:
        return {
            key: TypeAdapter(section_class).dump_python(
                self.section_instances[key], mode="json"
            )
            for key, section_class in self.section_classes.items()
        }

    def section(self, key: str) -> Callable:
        def inner(cls: type):
            cls = dataclass(cls)
            self.section_classes[key] = cls
            inst = parse_python(self.data.get(key, {}), cls)
            self.section_instances[key] = inst
            return inst

        return inner


def configconfig(
    name: str,
    data: dict | None = None,
    path: Path | None = None,
    datadir: Path | None = None,
    configdir: Path | None = None,
    configcls: type[ConfigConfigType] = AppdirConfigConfig,
) -> ConfigConfigType:
    return configcls(
        name,
        override_data=data,
        override_path=path,
        override_datadir=datadir,
        override_configdir=configdir,
    )
