"""CLI for simple PDF manipulation utilities."""

import re
import warnings
from pathlib import Path

import typer
from pypdf import PdfReader, PdfWriter
from rich.console import Console
from rich.panel import Panel

# Disable PyPDF warnings
warnings.filterwarnings("ignore")
cli = typer.Typer()


def _iter_numbered_pdfs(wd: Path) -> list[Path]:
    num_pdf_re = r"(\d+)[^\d].*\.pdf"
    pdfs = wd.glob("*.pdf")
    pdfs = (
        (int(m.group(1)), p) for p in pdfs if (m := re.match(num_pdf_re, str(p.name)))
    )
    pdfs = (p[1] for p in sorted(pdfs))
    yield from pdfs


def _iterprint(it):
    for i in it:
        print(i)
        yield i


@cli.command()
def show(src: Path) -> None:
    """Attempt to display text content of PDF."""

    console = Console()
    reader = PdfReader(src)
    for i, page in enumerate(reader.pages):
        content = Panel(page.extractText(), title=f"{i+1}")
        console.print(content)


@cli.command()
def nsplit(src: Path, wd: Path = Path.cwd()):
    """Split the document into single-page documents.

    For example, nsplit('threepages.pdf') produces:
    1-threepages.pdf
    2-threepages.pdf
    3-threepages.pdf
    """
    reader = PdfReader(src)
    for i, page in enumerate(reader.pages):
        writer = PdfWriter()
        writer.add_page(page)
        dest = src.with_stem(f"{i}-{src.stem}")
        writer.write(dest)
        print(dest.resolve())


@cli.command()
def nmerge(dest: Path, wd: Path = Path.cwd()):
    """Merge a document from numbered segments.

    For example, nmerge() with a directory that contains:
    1-threepages.pdf
    2-threepages.pdf
    3-threepages.pdf

    Will will merge the 3 documents into one.
    """

    writer = PdfWriter()
    for src in _iterprint(_iter_numbered_pdfs(wd)):
        for page in PdfReader(src).pages:
            writer.add_page(page)
    writer.write(dest)
    print(dest.resolve())


@cli.command()
def interleave(dest: Path, wd: Path = Path.cwd()):
    """Cycle through numbered pdfs in the current directory, taking one page from each per round.
    Will merge a double-sided document scanned as fronts and backs."""

    iter_inputs = _iterprint(_iter_numbered_pdfs(wd))
    readers = [PdfReader(p) for p in iter_inputs]
    writer = PdfWriter()
    page = 0
    while True:
        readers = [i for i in readers if page < len(i.pages)]
        if not readers:
            break
        for reader in readers:
            writer.add_page(reader.getPage(page))
        page += 1
    writer.write(dest)


def _get_matching_paths(matcher, wd, pattern):
    for path in wd.glob(pattern):
        if result := matcher(path.name):
            yield (result, path)


class LengthMismatch(Exception):
    pass


def _duplexify(front: Path, back: Path, out: Path):
    rfront, rback = PdfReader(front), PdfReader(back)
    if (lfront := len(rfront.pages)) != (lback := len(rback.pages)):
        print("Front & back must be same length:")
        print(f"{lfront: >4}pg: {front}")
        print(f"{lback: >4}pg: {back}")
        raise LengthMismatch()
    writer = PdfWriter()
    page = 0
    while True:
        if page == len(rfront.pages):
            break
        writer.add_page(rfront.pages[page])
        if page < len(rback.pages):
            writer.add_page(rback.pages[::-1][page])
        page += 1
    writer.write(out)


@cli.command()
def duplexify(wd: Path = Path.cwd()):
    """Takes simplex front and reverse simplex back and joins to duplex.

    Files should be named:
        abc-front.pdf
        abc-back.pdf
    Result:
        abc.pdf
    """

    duplex_re = r"(.*?)\s*{}.pdf"

    def match_front(s):
        return (
            m.group(1)
            if (m := re.match(duplex_re.format("front"), s, re.IGNORECASE))
            else None
        )

    def match_back(s):
        return (
            m.group(1)
            if (m := re.match(duplex_re.format("back"), s, re.IGNORECASE))
            else None
        )

    fronts = {
        name: path for name, path in _get_matching_paths(match_front, wd, "*.pdf")
    }
    backs = {name: path for name, path in _get_matching_paths(match_back, wd, "*.pdf")}
    sfronts, sbacks = set(fronts), set(backs)
    sduplexes = sfronts & sbacks

    if no_backs := sfronts - sduplexes:
        print("Missing back scans for:")
        print(*("\t" + fronts[name].name for name in no_backs), sep="\n")

    if no_fronts := sbacks - sduplexes:
        print("Missing front scans for:")
        print(*("\t" + backs[name].name for name in no_fronts), sep="\n")

    pdfs = ((fronts[name], backs[name], name) for name in sduplexes)
    for front, back, name in pdfs:
        out = front.with_stem(name)
        try:
            _duplexify(front, back, out)
            print("\r" f'Wrote "{out.name}".')
            front.unlink()
            back.unlink()
        except LengthMismatch:
            pass


if __name__ == "__main__":
    cli()
