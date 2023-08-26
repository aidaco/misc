from uuid import uuid4
from typing import TypeVar, Generic
from dataclasses import dataclass, fields

T = TypeVar('T')


@dataclass
class DCTable(Generic[T]):
    type: type[T]
    name: str
    columns: list

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
    return DCTable(
        type=cls,
        name=cls.__name__,
        columns=fields(cls)
    )
