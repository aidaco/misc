import re

# Disable PyPDF warnings
import warnings
from pathlib import Path

import typer
from PyPDF2 import PdfReader, PdfWriter
from rich.console import Console
from rich.panel import Panel

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
        print(f"./{dest.relative_to(wd)}")


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


@cli.command()
def interleave(dest: Path, wd: Path = Path.cwd()):
    """Cycle through numbered pdfs in the current directory, taking one page from each per round.
    Will merge a double-sided document scanned as fronts and backs."""

    iter_inputs = _iterprint(_iter_numbered_pdfs(wd))
    readers = [PdfReader(p) for p in iter_inputs]
    writer = PdfWriter()
    page = 0
    while True:
        readers = [i for i in readers if page < i.numPages]
        if not readers:
            break
        for reader in readers:
            writer.add_page(reader.getPage(page))
        page += 1
    writer.write(dest)

def _duplexify(front: Path, back: Path, out: Path):
    front, back = PdfReader(front), PdfReader(back)
    writer = PdfWriter()
    page = 0
    while True:
        if page == front.numPages:
            break
        writer.add_page(front.pages[page])
        if page < back.numPages:
            writer.add_page(back.pages[::-1][page])
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
    

    pdfs = list(wd.glob('*.pdf'))
    front_re = r'(.*?)\s*front.pdf'
    for pdf in pdfs:
        if not (m := re.match(front_re, pdf.name, re.IGNORECASE)):
            continue
        name = m.group(1)
        back_re = rf'{name}\s*back.pdf'
        back = [p for p in pdfs if re.match(back_re, p.name, re.IGNORECASE)][0]
        if not back:
            print(f'No back for front {pdf}')
            continue
        out = pdf.with_stem(name)
        print(f'Duplexifying "{out.name}"')
        _duplexify(pdf, back, out)
        pdf.unlink()
        back.unlink()
        
if __name__ == "__main__":
    cli()
