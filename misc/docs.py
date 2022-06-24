import ast
import pathlib
import re


def dechevron(doc: str):
    return "\n".join(re.findall(".*>>>(.*)", doc))


def loadfndoc(n: ast.FunctionDef) -> str:
    e = n.body[0]
    if not isinstance(e, ast.Expr) or not isinstance(e.value, ast.Constant):
        return ""
    else:
        return e.value.value


def loadclsdoc(n: ast.ClassDef) -> tuple[str, dict[str, str]]:
    """Read the class and method docstrings."""

    e = n.body[0]
    if not isinstance(e, ast.Expr) or not isinstance(e.value, ast.Constant):
        clsdoc = ""
    else:
        clsdoc = e.value.value
    mthdocs, intclsdocs = {}, {}
    for e in n.body[1:]:
        match e:  # type: ignore
            case ast.FunctionDef():
                mthdocs[e.name] = loadfndoc(e)
            case ast.ClassDef():
                intlclsdocs[e.name] = loadclsdocs(e)
    return clsdoc, mthdocs, intclsdocs


def loaddocs(
    path: pathlib.Path,
) -> tuple[dict[str, str], dict[str, tuple[str, dict, dict]]]:
    with path.open() as io:
        data = io.read()
    body = ast.parse(data).body
    fndocs = {n.name: loadfndoc(n) for n in body if isinstance(n, ast.FunctionDef)}
    clsdocs = {n.name: loadclsdoc(n) for n in body if isinstance(n, ast.ClassDef)}
    return fndocs, clsdocs


def dechevrondocs(fndocs, clsdocs):
    fndocs = {name: dechevron(doc) for name, doc in fndocs.items()}
    clsdocs = {
        name: (
            ("", {})
            if len(doc) == 0
            else (
                dechevron(doc[0]),
                *dechevrondocs(doc[1], doc[2]),
            )
        )
        for name, doc in clsdocs.items()
    }
    return fndocs, clsdocs


def iterpy(d: str = "."):
    yield from sorted(pathlib.Path(d).glob("**/*.py"))


def main():
    print([dechevrondocs(*loaddocs(file)) for file in iterpy()])


if __name__ == "__main__":
    main()
