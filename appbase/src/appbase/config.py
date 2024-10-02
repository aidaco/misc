from dataclasses import dataclass, field
import io
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    Literal,
    Mapping,
    Protocol,
    Self,
    TextIO,
    TypeAlias,
    runtime_checkable,
)
import json
import typing

from pydantic import BaseModel, TypeAdapter
import appdirs
import toml
import yaml


type Format = Literal["toml", "json", "yaml", "unsafe_yaml"]
FORMATS: set[str] = {"toml", "json", "yaml", "safe_yaml"}


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


def load_path(path: Path, format: Format | None = None) -> dict:
    if not path.exists():
        return {}
    elif path.is_dir():
        raise ValueError(f"Expected a file not a directory: {path}")
    _format = format or path.suffix.lstrip(".")
    if not _format:
        raise ValueError(f"Unknown extension {path}, pass the format as an argument.")
    assert _format in FORMATS
    _format = typing.cast(Format, _format)
    with path.open("rb") as file:
        return read_format(file, _format)


def dump_path(
    value: Any,
    path: Path,
    format: Format | None = None,
) -> None:
    if format is None:
        format = typing.cast(Format, path.suffix.lstrip("."))
        assert format in FORMATS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as file:
        write_format(value, file, format)


Model: TypeAlias = BaseModel


class ConfigConfigType(Protocol):
    def load(self) -> dict: ...
    def dump(self, data: dict) -> None: ...


@dataclass
class AppdirConfigConfig:
    name: str
    override_data: dict | None = None
    override_path: Path | None = None

    @property
    def configpath(self) -> Path:
        return self.override_path or self.configdir / "config.toml"

    @property
    def configdir(self) -> Path:
        return Path(appdirs.user_config_dir(self.name)).resolve()

    def load(self, format: Format | None = None, path: Path | None = None) -> dict:
        if self.override_data is not None:
            return self.override_data
        return load_path(path or self.configpath, format)

    def dump(
        self, data: dict, format: Format | None = None, path: Path | None = None
    ) -> None:
        dump_path(data, path or self.configpath, format)

    def dumps(self, data: dict, format: Format = "toml") -> str:
        return dump_str(data, format)


@dataclass
class Config[CC: ConfigConfigType]:
    config: CC
    data: Mapping = field(default_factory=dict)
    section_classes: dict[str, type] = field(default_factory=dict)
    section_instances: dict[str, Any] = field(default_factory=dict)

    def get_section(self, key: str) -> Any:
        return parse_python(self.data.get(key, {}), self.section_classes[key])

    def dump_section(self, key: str) -> dict:
        return dump_python(self.section_instances[key])

    def dump_all(self) -> dict[str, dict]:
        return {key: self.dump_section(key) for key in self.section_instances}

    def write(self, format: Format | None = None, path: Path | None = None) -> None:
        self.config.dump(self, format, path)

    def section(self, key: str) -> Callable:
        def inner(cls: type):
            cls = dataclass(cls)
            self.section_classes[key] = cls
            self.section_instances[key] = inst = self.get_section(key)
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


@runtime_checkable
class RSourceType(Protocol):
    def load(self) -> dict: ...


@runtime_checkable
class RWSourceType(Protocol):
    def load(self) -> dict: ...
    def dump(self, data: dict) -> None: ...


SourceType: TypeAlias = RSourceType | RWSourceType


@dataclass
class DictSource:
    data: dict

    def load(self) -> dict:
        return self.data

    def dump(self, data: dict) -> None:
        self.data = data


@dataclass
class PathSource:
    path: Path
    format: Format | None = None

    def load(self) -> dict:
        return load_path(self.path, self.format)

    def dump(self, data: dict) -> None:
        dump_path(data, self.path, self.format)


@dataclass
class AppdirsSource:
    name: str

    @property
    def configpath(self) -> Path:
        return self.configdir / "config.toml"

    @property
    def configdir(self) -> Path:
        return Path(appdirs.user_config_dir(self.name)).resolve()

    @property
    def datadir(self) -> Path:
        return Path(appdirs.user_config_dir(self.name)).resolve()

    def load(self, format: Format | None = None, path: Path | None = None) -> dict:
        return load_path(path or self.configpath, format)

    def dump(
        self, data: dict, format: Format | None = None, path: Path | None = None
    ) -> None:
        dump_path(data, path or self.configpath, format)


@dataclass
class ConfigFromSource[S: SourceType]:
    source: S
    data: Mapping = field(default_factory=dict)
    section_classes: dict[str, type] = field(default_factory=dict)
    section_instances: dict[str, Any] = field(default_factory=dict)

    def get_section(self, key: str) -> Any:
        return parse_python(self.data.get(key, {}), self.section_classes[key])

    def section_to_dict(self, key: str) -> dict:
        return dump_python(self.section_instances[key])

    def to_dict(self) -> dict[str, dict]:
        return {key: self.section_to_dict(key) for key in self.section_instances}

    @classmethod
    def load(cls, source: SourceType) -> Self:
        return cls(source, source.load())

    def dump(self, source: SourceType | None = None) -> None:
        src = source or self.source
        match src:
            case RWSourceType():
                src.dump(self.to_dict())
            case _:
                raise ValueError(f"Cannot dump to read-only source {src}")

    def section(self, key: str) -> Callable:
        def inner(cls: type):
            cls = dataclass(cls)
            self.section_classes[key] = cls
            self.section_instances[key] = inst = self.get_section(key)
            return inst

        return inner


def from_appname[ST: AppdirsSource](
    name: str, cls: type[ST] = AppdirsSource
) -> ConfigFromSource[ST]:
    return ConfigFromSource.load(cls(name))
