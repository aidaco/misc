from uuid import uuid4
from typing import TypeVar, Generic
from dataclasses import dataclass, fields
from functools import cached_property

T = TypeVar('T')


@dataclass
class DCTable(Generic[T]):
    type: type[T]

    @cached_property
    def name(self):
        return self.type.__name__

    @cached_property
    def columns(self):
        return fields(self)    

    def create(self):
        print(
            f'CREATE TABLE {self.name}'
            f'({", ".join(f"{col.name} {col.type.__name__}" for col in self.columns)});'
        )

    def insert(self, **args):
        print(
            f'INSERT INTO {self.name} '
            f'VALUES ({", ".join(f"{k}={v}" for k,v in args)});'
        )
        return self.type({**args, 'id': str(uuid4())})

    def update(self, id: int, values, conditions):
        print(
            f'UPDATE {self.name} '
            f'SET {", ".join(f"{k} = {v}" for k,v in values)}'
            f'WHERE {conditions};'
        )


def dctable(cls: type[T]) -> DCTable[T]:
    return DCTable(type=cls)


@dataclass(frozen=True, slots=True)
class Record:
    id: str

    @classmethod
    def create(cls, **kwargs):
        return cls(id=str(uuid4()), **kwargs)

    def asdict(self):
        return {field.name: getattr(self, field.name) for field in fields(self)}

    def sub(self, **kwargs):
        return type(self)(**(self.asdict() | kwargs))
