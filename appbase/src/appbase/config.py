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
    TextIO,
    TypeAlias,
    runtime_checkable,
    overload,
)
import json
import typing

from pydantic import BaseModel, TypeAdapter
import platformdirs
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
    raise ValueError(f"Unsupported format: {format}.")


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
                case io.TextIOBase():
                    json.dump(value, file)
                case io.BufferedIOBase():
                    buffer = io.StringIO()
                    json.dump(value, buffer)
                    file.write(buffer.getvalue().encode())
        case "safe_yaml":
            yaml.dump(value, file)
        case "yaml":
            yaml.dump(value, file)
        case _:
            raise ValueError(f"Unsupported format: {format}.")


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
    raise ValueError(f"Unsupported format: {format}.")


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


@runtime_checkable
class RSourceType(Protocol):
    def load(self) -> Mapping[str, Any]: ...


@runtime_checkable
class RWSourceType(Protocol):
    def load(self) -> Mapping[str, Any]: ...
    def dump(self, data: Mapping[str, Any]) -> None: ...


SourceType: TypeAlias = RSourceType | RWSourceType


@dataclass
class StrSource:
    data: str
    format: Format

    def load(self) -> dict:
        buffer = io.StringIO(self.data)
        data = read_format(buffer, self.format)
        return data

    def dump(self, data: dict) -> None:
        buffer = io.StringIO()
        write_format(data, buffer, self.format)
        self.data = buffer.getvalue()


@dataclass
class MappingSource:
    data: Mapping

    def load(self) -> Mapping:
        return self.data

    def dump(self, data: Mapping) -> None:
        self.data = data


@dataclass
class PathSource:
    path: Path
    format: Format | None = None

    def load(self) -> dict:
        return load_path(self.path, self.format)

    def dump(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        dump_path(data, self.path, self.format)


@dataclass
class PlatformdirsSource:
    name: str

    @property
    def configpath(self) -> Path:
        return self.configdir / "config.toml"

    @property
    def configdir(self) -> Path:
        return Path(platformdirs.user_config_dir(self.name)).resolve()

    @property
    def datadir(self) -> Path:
        return Path(platformdirs.user_data_dir(self.name)).resolve()

    def load(self, format: Format | None = None, path: Path | None = None) -> dict:
        return load_path(path or self.configpath, format)

    def dump(
        self, data: dict, format: Format | None = None, path: Path | None = None
    ) -> None:
        path = path or self.configpath
        path.parent.mkdir(parents=True, exist_ok=True)
        dump_path(data, path or self.configpath, format)


@dataclass
class ConfigConfig[S: SourceType]:
    source: S
    root_class: type | None = None
    root_instance: Any | None = None
    section_classes: dict[str, type] = field(default_factory=dict)
    section_instances: dict[str, Any] = field(default_factory=dict)
    data_cache: Mapping[str, Any] | None = None

    @property
    def data(self) -> Mapping:
        if self.data_cache is None:
            self.data_cache = self.source.load()
        return self.data_cache

    def get_section(self, key: str) -> Any:
        if key not in self.section_instances:
            cls = self.section_classes[key]
            data = self.data.get(key, {})
            self.section_instances[key] = parse_python(data, cls)
        return self.section_instances[key]

    def section_to_dict(self, key: str) -> dict:
        return dump_python(self.section_instances[key])

    def get_root(self) -> Any:
        assert self.root_class is not None
        if self.root_instance is None:
            self.root_instance = parse_python(self.data, self.root_class)
        return self.root_instance

    def root_to_dict(self) -> dict:
        assert self.root_instance is not None
        return dump_python(self.root_instance)

    def to_dict(self) -> dict[str, dict]:
        return self.root_to_dict() | {
            key: self.section_to_dict(key) for key in self.section_instances
        }

    def dump(self, source: SourceType | None = None) -> None:
        src = source or self.source
        match src:
            case RWSourceType():
                src.dump(self.to_dict())
            case _:
                raise ValueError(f"Cannot dump to read-only source {src}")

    def dumps(self, format: Format = "toml") -> str:
        src = StrSource("", format)
        self.dump(src)
        return src.data

    def section[M](self, key: str) -> Callable[[type[M]], Callable[[], M]]:
        def inner(cls: type[M]):
            cls = dataclass(cls)
            self.section_classes[key] = cls
            return lambda: self.get_section(key)

        return inner

    def root[M](self, cls: type[M]) -> Callable[[], M]:
        cls = dataclass(cls)
        self.root_class = cls

        def load():
            self.root_instance = inst = self.get_root()
            return inst

        return load

    @overload
    @staticmethod
    def load[SS: SourceType](*, source: SS) -> "ConfigConfig[SS]": ...
    @overload
    @staticmethod
    def load(*, name: str) -> "ConfigConfig[PlatformdirsSource]": ...
    @overload
    @staticmethod
    def load(
        *, path: Path, format: Format | None = None
    ) -> "ConfigConfig[PathSource]": ...
    @overload
    @staticmethod
    def load(*, text: str, format: Format = "toml") -> "ConfigConfig[StrSource]": ...
    @overload
    @staticmethod
    def load(*, mapping: Mapping) -> "ConfigConfig[MappingSource]": ...
    @staticmethod
    def load(
        *, source=None, name=None, path=None, text=None, mapping=None, format=None
    ) -> "ConfigConfig":
        if source:
            src = source
        elif name:
            src = PlatformdirsSource(name)
        elif path:
            src = PathSource(path, format)
        elif text:
            src = StrSource(text, format or "toml")
        elif mapping:
            src = MappingSource(mapping)
        else:
            raise ValueError("Must pass a kwarg.")
        return ConfigConfig(src)

    @overload
    def reload(self) -> None: ...
    @overload
    def reload(self, *, source: SourceType) -> None: ...
    @overload
    def reload(self, *, name: str) -> None: ...
    @overload
    def reload(self, *, path: Path, format: Format = "toml") -> None: ...
    @overload
    def reload(self, *, text: str, format: Format = "toml") -> None: ...
    @overload
    def reload(self, *, mapping: Mapping) -> None: ...
    def reload(
        self, *, source=None, name=None, path=None, text=None, mapping=None, format=None
    ) -> None:
        if source:
            self.source = source
        elif name:
            self.source = PlatformdirsSource(name)  # type: ignore
        elif path:
            self.source = PathSource(path, format)  # type: ignore
        elif text and format:
            self.source = StrSource(text, format)  # type: ignore
        elif mapping:
            self.source = MappingSource(mapping)  # type: ignore
        self.data_cache = None
        self.root_instance = None
        self.section_instances = dict()


load = ConfigConfig.load
