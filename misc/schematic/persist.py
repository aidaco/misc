from .schema import SchemaInfo, FieldInfo

SQL_TYPES = {
    bool: 'INTEGER',
    int: 'INTEGER',
    float: 'REAL',  
    str: 'TEXT',
    bytes: 'BLOB',
}

def create(schema: SchemaInfo) -> str:
    return f'CREATE TABLE {schema.name}({", ".join(f"{f.name} {SQL_TYPES[f.type]}" for f in schema.fields)})'

def insert(schema: SchemaInfo, values) -> str:
    return f'INSERT INTO {schema.name} VALUES ({", ".join(map(repr, values))})'