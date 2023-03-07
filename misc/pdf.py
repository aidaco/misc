"""CLI for simple PDF manipulation utilities."""

import re
import warnings
from pathlib import Path

import typer
from PyPDF2 import PdfFileReader, PdfFileWriter
from rich.console import Console
from rich.panel import Panel

# Disable PyPDF warnings
warnings.filterwarnings("ignore")


cli = typer.Typer()


@cli.command()
def show(pdf_path: Path) -> None:
    """Attempt to display text content of PDF."""

    console = Console()
    with pdf_path.open("rb") as io:
        pdf = PdfFileReader(io)
        for i, pg in enumerate(pdf.pages):
            console.print(Panel(pg.extractText(), title=f"{i+1}"))


@cli.command()
def nsplit(pdf: Path, wd: Path):
    """Split the document into single-page documents.

    For example, nsplit('threepages.pdf') produces:
    1-threepages.pdf
    2-threepages.pdf
    3-threepages.pdf
    """
    f = PdfFileReader(pdf.open("rb"))
    for i, pg in enumerate(f.pages):
        w = PdfFileWriter()
        w.add_page(pg)
        o = pdf.with_stem(f"{i}-{pdf.stem}")
        w.write(o)
        print(f"./{o.relative_to(wd)}")


@cli.command()
def nmerge(pdf: Path, wd: Path):
    """Merge a document from numbered segments.

    For example, nmerge() with a directory that contains:
    1-threepages.pdf
    2-threepages.pdf
    3-threepages.pdf

    Will will merge the 3 documents into one.
    """
    o = PdfFileWriter()
    pdfs = wd.glob("*.pdf")
    def matches(s):
        return re.match("(\\d+)[^\\d].*", str(s)) is not None
    def num(s):
        return int(re.match("(\\d+)[^\\d].*", str(s)).group(1))
    for f in sorted((p for p in pdfs if matches(p)), key=num):
        print(f)
        for pg in PdfFileReader(f).pages:
            o.addPage(pg)
    o.write(pdf.open("wb"))


if __name__ == "__main__":
    cli()
