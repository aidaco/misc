OPTIMIZE_OPEN = """PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;"""

OPTIMIZE_CLOSE = """PRAGMA analysis_limit = {analysis_limit};
PRAGMA optimize;"""


stmts = r"""
[create_base]
CREATE [TEMPORARY] TABLE [IF NOT EXISTS] [schema.]table (
    [for name, type, constraints in columns]
    name [type] [*constraints ]
    [\for]
    [*table_constraints,]
) [WITHOUT ROWID];

[insert_base]
INSERT [OR [ABORT|FAIL|IGNORE|REPLACE|ROLLBACK]] INTO [schema.]table ([*columns,]) VALUES ([*values,]);

[select_base]
SELECT [ALL|DISTINCT] *result_columns
[FROM *table_or_subquery,|JOIN table ON join_condition]
[WHERE condition]
[[UNION|UNION ALL|INTERSECT|EXCEPT] subquery]
[ORDER BY column]
[LIMIT count [OFFSET offset]]
[GROUP BY column [HAVING filter]];

[update_base]
UPDATE [OR [ABORT|FAIL|IGNORE|REPLACE|ROLLBACK]] table
SET
    [for column, value in values]
    column=value,
    [\for]
WHERE [condition];

[delete_base]
DELETE FROM [schema.]table WHERE condition;
"""


def create(name, columns, table_constraints=(), exist_ok=True, rowid=True):
    exists = " IF NOT EXISTS" if exist_ok else ""
    column_defs = (
        " ".join([name, typ, " ".join(constraints)] if constraints else [name, typ])
        for name, typ, constraints in columns
    )
    schema = ", ".join([*column_defs, *table_constraints])
    rowid = " WITHOUT ROWID" if not rowid else ""

    return f"CREATE TABLE{exists} {name}({schema}){rowid}"


def insert(name, columns, failure_mode=None):
    # fail_modes = ["ABORT", "FAIL", "IGNORE", "REPLACE", "ROLLBACK"]
    failure_mode = f" OR {failure_mode.upper()}" if failure_mode else ""
    columns = ", ".join(columns)
    values = ", ".join("?" * len(columns))
    return f"INSERT{failure_mode} INTO {name} ({columns}) VALUES ({values})"


def select(
    result="*",
    source="",
    join=None,
    where=None,
    subquery=None,
    order=None,
    limit=None,
    offset=None,
    group=None,
    having=None,
    distinct=False,
):
    distinct = " DISTINCT" if distinct else ""
    _from = f" FROM {source}" if source else ""
    join = f" JOIN {join[0]} ON {join[1]}" if join else ""
    where = f" WHERE {where}" if where else ""
    # Compound types ['UNION', 'UNION ALL', 'INTERSECT', 'EXCEPT']
    compound = f" {subquery[0]} {subquery[1]}" if subquery else ""
    order = f" ORDER BY {order}" if order else ""
    limit = f" LIMIT {limit}" if limit else ""
    offset = f" OFFSET {offset}" if offset else ""
    group = f' GROUP BY {group}{f" HAVING {having}" if having else ""}' if group else ""
    return (
        f"SELECT{distinct} {result}{_from}{join}{where}{compound}{order}{limit}{group}"
    )


def update(name, columns, values, where, failure_mode=None):
    # fail_modes = ["ABORT", "FAIL", "IGNORE", "REPLACE", "ROLLBACK"]
    failure_mode = f" OR {failure_mode.upper()}" if failure_mode else ""
    assignments = ", ".join(f"{c}={v}" for c, v in zip(columns, values))
    where = f" WHERE {where}" if where else ""
    return f"UPDATE{failure_mode} {name} SET {assignments}{where}"


def delete(name, where=None):
    where = f" WHERE {where}" if where else ""
    return f"DELETE FROM {name}{where}"


# Parsing stuff
Name = "[_a-z][_a-z0-9]*"
Integer = "[1-9](?:_?[0-9])*"
Float = r"(?:[0-9](?:_?[0-9])*\.(?:[0-9](?:_?[0-9])*)?)|(?:\.[0-9](?:_?[0-9])*)"
