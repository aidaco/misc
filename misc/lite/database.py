from dataclasses import fields
from typing import Type
import uuid


class Database:
    def __init__(self, uri: str, **tables: Type):
        self.uri = uri
        self.tables = {k: Table(k, v) for k, v in tables.items()}
        for k, v in self.tables.items():
            setattr(self, k, v)

class Table:
    def __init__(self, name: str, model: Type):
        self.name = name
        self.fields = fields(model)

    def init(self):
        stmt = f"CREATE TABLE IF NOT EXISTS {self.name}"
        stmt += "(id text primary key," + ",".join(f"{f.name} {f.type}" for f in self.fields) + ")"
        stmt += ";"
        print(stmt)

    def create(self, *args):
        stmt = f'INSERT INTO {self.name}({",".join(["id"]+[f.name for f in self.fields])}) VALUES({uuid.uuid4()}, {",".join("?"*len(args))});'
        print(stmt, args)

    def get(self, id: int):
        stmt = f"SELECT * FROM {self.name} WHERE id = ? LIMIT 1;"
        print(stmt, id)

    def find(self, predicate):
        stmt = f"SELECT * FROM {self.name} WHERE {predicate};"
        print(stmt)

    def update(self, obj):
        stmt = f'UPDATE {self.name} SET {",".join(f"{f.name} = {getattr(obj, f.name)}" for f in self.fields)} WHERE id = {obj.id};'
        print(stmt)

    def delete(self, obj):
        stmt = f"DELETE FROM {self.name} WHERE id = ?;"
        print(stmt, obj.id)
