import sqlite3
import dataclasses
import re
from typing import (
    overload,
    Any,
    Self,
    get_origin,
    Annotated,
    get_args,
    TypeAlias,
    Iterator,
    get_type_hints,
    Literal,
)
from types import UnionType
from itertools import chain
from datetime import datetime, timedelta
from pathlib import Path

import pydantic

type ConflictResolutionType = Literal["ABORT", "ROLLBACK", "FAIL", "IGNORE", "REPLACE"]
JSONB: TypeAlias = Annotated[bytes, "jsonb"]
INTPK: TypeAlias = Annotated[int, "PRIMARY KEY"]


@dataclasses.dataclass
class ColumnDef:
    name: str
    dtype: str | None
    contraints: str | None

    def __str__(self) -> str:
        parts = [self.name]
        if self.dtype:
            parts.append(self.dtype)
        if self.contraints:
            parts.append(self.contraints)
        return " ".join(parts)

    @classmethod
    def from_annotation(
        cls,
        name: str,
        annotation: Any,
        type_map: dict[type | Any, str] = {
            str: "TEXT",
            int: "INTEGER",
            float: "REAL",
            bytes: "BLOB",
            datetime: "DATETIME",
            timedelta: "TIMEDELTA",
            Path: "PATH",
            JSONB: "JSONB",
        },
    ) -> Self:
        sqlite_type = None
        constraints = None
        not_null = True

        def unpack_type(t):
            nonlocal sqlite_type, not_null, constraints
            try:
                sqlite_type = type_map[t]
                return
            except KeyError:
                pass
            origin = get_origin(t)
            if origin is Annotated:
                match get_args(t):
                    case (_type, _def):
                        constraints = _def
                        unpack_type(_type)
                        return
                    case _:
                        raise TypeError(f"Can only accept one str annotation: {t}")
            elif origin is UnionType:
                match get_args(t):
                    case (_type, None) | (None, _type):
                        not_null = False
                        unpack_type(_type)
                        return
                    case _:
                        raise TypeError(f"Unions not supported, except | None: {t}")

        unpack_type(annotation)
        if constraints is None and not_null is not None:
            constraints = "NOT NULL"
        elif constraints is not None and not_null is not None:
            constraints = f"NOT NULL {constraints}"

        return cls(name, sqlite_type, constraints)


def table_name_for(model: type, replace_regex=re.compile("(?<!^)(?=[A-Z])")) -> str:
    return replace_regex.sub("_", model.__name__).casefold()


def annotations_from(model: type) -> Iterator[tuple[str, Any]]:
    if dataclasses.is_dataclass(model):
        yield from ((field.name, field.type) for field in dataclasses.fields(model))
    elif issubclass(model, pydantic.BaseModel):
        annotations = get_type_hints(model, include_extras=True)
        yield from ((name, annotations[name]) for name in model.model_fields)
    else:
        raise TypeError(f"Unsupported model type {model}.")


def extract_param(params: tuple, kwparams: dict) -> tuple | dict:
    if kwparams:
        if params:
            raise ValueError("Pass parameters by tuple OR dict, not both.")
        return kwparams

    match params:
        case (tuple() | dict() as p,):
            return p
        case (p,) if dataclasses.is_dataclass(p) and not isinstance(p, type):
            return dataclasses.asdict(p)
        case (p,) if isinstance(p, pydantic.BaseModel):
            return p.model_dump()
        case tuple():
            return params
        case _:
            raise ValueError(f"Invalid parameters: {params}")


@dataclasses.dataclass
class Statement[C: sqlite3.Cursor]:
    cursor: C | None

    @overload
    def execute(self, *params: Any) -> C: ...
    @overload
    def execute(self, **params: Any) -> C: ...
    @overload
    def execute(self, param: dict | tuple) -> C: ...
    def execute(self, *var_params, **kvar_params):
        assert self.cursor is not None
        params = extract_param(var_params, kvar_params)
        return self.cursor.execute(str(self), params)


@dataclasses.dataclass
class Create[C: sqlite3.Cursor](Statement[C]):
    table: str
    columns: list[ColumnDef]
    table_contraints: list[str]
    _if_not_exists: bool
    _strict: bool
    _without_rowid: bool

    @classmethod
    def from_model(
        cls,
        model: type,
        cursor: C | None = None,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> Self:
        table = table_name_for(model)
        columns = [
            ColumnDef.from_annotation(name, annotation)
            for name, annotation in annotations_from(model)
        ]
        return cls(cursor, table, columns, [], if_not_exists, strict, without_rowid)

    def if_not_exists(self, if_not_exists: bool = True) -> Self:
        self._if_not_exists = if_not_exists
        return self

    def strict(self, strict: bool = True) -> Self:
        self._strict = strict
        return self

    def without_rowid(self, without_rowid: bool = True) -> Self:
        self._without_rowid = without_rowid
        return self

    def __str__(self) -> str:
        stmt = "CREATE TABLE"
        stmt += " IF NOT EXISTS" if self._if_not_exists else ""
        stmt += " " + self.table
        stmt += f"({', '.join(chain(map(str, self.columns), self.table_contraints))})"
        table_options = []
        if self._strict:
            table_options.append("STRICT")
        if self._without_rowid:
            table_options.append("WITHOUT ROWID")
        if table_options:
            stmt += " " + ", ".join(table_options)
        return stmt


@dataclasses.dataclass
class Select[C: sqlite3.Cursor](Statement[C]):
    table: str
    _fields: list[str]
    _where: str | None
    _offset: int | None
    _limit: int | None
    _orderby: list[str] | None

    def where(self, expr: str | None = None) -> Self:
        self._where = expr
        return self

    def offset(self, value: int | None = None) -> Self:
        self._offset = value
        return self

    def limit(self, value: int | None = None) -> Self:
        self._limit = value
        return self

    def orderby(self, *terms: str) -> Self:
        self._orderby = list(terms)
        return self

    @classmethod
    def from_model(
        cls,
        model: type,
        table: str | None = None,
        cursor: C | None = None,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> Self:
        table = table or table_name_for(model)
        fields = [name for name, _ in annotations_from(model)]
        return cls(
            cursor,
            table,
            fields,
            where,
            offset,
            limit,
            orderby,
        )

    def __str__(self) -> str:
        stmt = "SELECT"
        stmt += f" * FROM {self.table}"
        stmt += f" WHERE {self._where}" if self._where else ""
        stmt += f" ORDER BY {', '.join(self._orderby)}" if self._orderby else ""
        stmt += f" LIMIT {self._limit}" if self._limit else ""
        stmt += f" OFFSET {self._offset}" if self._offset else ""
        return stmt


@dataclasses.dataclass
class Insert[C: sqlite3.Cursor](Statement[C]):
    table: str
    conflict_resolution: ConflictResolutionType | None
    columns: list[str]
    _values: list[str] | None
    _returning: list[str] | None
    _param: list[tuple | dict] | tuple | dict | None

    @classmethod
    def from_model(
        cls,
        model: type,
        cursor: C | None = None,
        conflict_resolution: ConflictResolutionType | None = None,
        columns: list[str] | None = None,
        values: list[str] | None = None,
        returning: list[str] | None = None,
    ) -> Self:
        table = table_name_for(model)
        cols = (
            columns
            if columns is not None
            else [name for name, _ in annotations_from(model)]
        )
        return cls(
            cursor,
            table,
            conflict_resolution,
            cols,
            values,
            returning,
            None,
        )

    def returning(self, *exprs: str) -> Self:
        self._returning = list(exprs) or None
        return self

    def conflict(self, conflict_resolution: ConflictResolutionType) -> Self:
        self.conflict_resolution = conflict_resolution
        return self

    def values(self, *params, **kwparams) -> Self:
        param = extract_param(params, kwparams)
        match self._param:
            case None:
                self._param = param
            case tuple() as p:
                assert type(p) is type(param)
                assert len(p) == len(param)
                self._param = [p, param]
                if self._values is not None:
                    return self
            case dict() as p:
                assert type(p) is type(param)
                assert len(p) == len(param)
                colset = set(self.columns)
                assert all(key in colset for key in p)
                self._param = [p, param]
                if self._values is not None:
                    return self
            case list() as ps:
                length = len(param)
                cls = type(param)
                assert all(len(i) == length for i in ps)
                assert all(type(i) is cls for i in ps)
                ps.append(param)
                if self._values is not None:
                    return self
        match param:
            case tuple():
                placeholders = ["?" for _ in self.columns]
            case dict():
                param_keys = set(param.keys())
                self.columns = [name for name in self.columns if name in param_keys]
                placeholders = [f":{name}" for name in self.columns]
        self._values = placeholders
        return self

    def __str__(self) -> str:
        stmt = "INSERT"
        stmt += f" OR {self.conflict_resolution}" if self.conflict_resolution else ""
        columns = ", ".join(self.columns)
        stmt += f" INTO {self.table}({columns})"
        if self._values is not None:
            values = ", ".join(self._values)
            stmt += f" VALUES ({values})"
        if self._returning is not None:
            returning = ", ".join(self._returning)
            stmt += f" RETURNING {returning}"
        return stmt

    def execute(self, *params, **kwparams) -> C:
        assert self.cursor is not None
        match self._param:
            case tuple() | dict() as param:
                return super().execute(param)
            case list() as params:
                return self.cursor.executemany(str(self), params)
            case _:
                return super().execute(*params, **kwparams)


@dataclasses.dataclass
class Update[C: sqlite3.Cursor](Statement[C]):
    _table: str
    _conflict_resolution: ConflictResolutionType | None
    _set: str | None
    _where: str | None
    _returning: list[str] | None
    _param: dict | None

    @classmethod
    def from_model(
        cls,
        model: type,
        cursor: C | None = None,
        conflict_resolution: ConflictResolutionType | None = None,
        set: str | None = None,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> Self:
        table = table_name_for(model)
        return cls(cursor, table, conflict_resolution, set, where, returning, None)

    @overload
    def set(self, expr: str) -> Self: ...
    @overload
    def set(self, *params, **kwparams) -> Self: ...
    def set(self, *params, **kwparams):
        match (params, kwparams):
            case ((str(expr),), {**kw}) if not kw:
                self._set = expr
            case _:
                param = extract_param(params, kwparams)
                match param:
                    case dict():
                        self._set = ", ".join(f"{name}=:{name}" for name in param)
                        self._param = (
                            (self._param | param) if self._param is not None else param
                        )
                    case _:
                        raise TypeError("Must pass update params as dict or kwargs")
        return self

    @overload
    def where(self, expr: str) -> Self: ...
    @overload
    def where(self, *params, **kwparams) -> Self: ...
    def where(self, *params, **kwparams):
        match (params, kwparams):
            case ((str(expr),), {**kw}) if not kw:
                self._where = expr
            case _:
                param = extract_param(params, kwparams)
                match param:
                    case dict():
                        self._where = " AND ".join(f"{name}=:{name}" for name in param)
                        self._param = (
                            (self._param | param) if self._param is not None else param
                        )
                    case _:
                        raise TypeError("Must pass update params as dict or kwargs")
        return self

    def returning(self, *exprs: str) -> Self:
        self._returning = list(exprs) or None
        return self

    def conflict(self, conflict_resolution: ConflictResolutionType) -> Self:
        self.conflict_resolution = conflict_resolution
        return self

    def __str__(self) -> str:
        stmt = "UPDATE"
        stmt += f" OR {self._conflict_resolution}" if self._conflict_resolution else ""
        stmt += f" {self._table} SET {self._set}"
        stmt += f" WHERE {self._where}" if self._where else ""
        stmt += f" RETURNING {', '.join(self._returning)}" if self._returning else ""
        return stmt

    def execute(self, *params, **kwparams) -> C:
        assert self.cursor is not None
        if self._param:
            return super().execute(self._param)
        return super().execute(*params, **kwparams)


@dataclasses.dataclass
class ModelStatements[C: sqlite3.Cursor]:
    model: type
    cursor: C | None = None

    def create(
        self,
        if_not_exists: bool = False,
        strict: bool = False,
        without_rowid: bool = False,
    ) -> Create[C]:
        return Create.from_model(
            model=self.model,
            cursor=self.cursor,
            if_not_exists=if_not_exists,
            strict=strict,
            without_rowid=without_rowid,
        )

    def insert(
        self,
        conflict_resolution: ConflictResolutionType | None = None,
        columns: list[str] | None = None,
        values: list[str] | None = None,
        returning: list[str] | None = None,
    ) -> Insert[C]:
        return Insert.from_model(
            model=self.model,
            cursor=self.cursor,
            conflict_resolution=conflict_resolution,
            columns=columns,
            values=values,
            returning=returning,
        )

    def select(
        self,
        where: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        orderby: list[str] | None = None,
    ) -> Select[C]:
        return Select.from_model(
            model=self.model,
            cursor=self.cursor,
            where=where,
            offset=offset,
            limit=limit,
            orderby=orderby,
        )

    def update(
        self,
        conflict_resolution: ConflictResolutionType | None = None,
        set: str | None = None,
        where: str | None = None,
        returning: list[str] | None = None,
    ) -> Update[C]:
        return Update.from_model(
            model=self.model,
            cursor=self.cursor,
            conflict_resolution=conflict_resolution,
            set=set,
            where=where,
            returning=returning,
        )


def sql[C: sqlite3.Cursor](model: type, cursor: C | None = None) -> ModelStatements[C]:
    return ModelStatements(model, cursor)
