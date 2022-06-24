import functools
import inspect
import itertools
import typing
from pathlib import Path

from PyPDF2 import PdfFileMerger, PdfFileReader, PdfFileWriter
from rich.console import Console
from rich.panel import Panel

def _autopath(func: typing.Callable) -> typing.Callable:
    sig = inspect.signature(func)

    @functools.wraps(func)
    def wrap(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        for name in bound.arguments:
            if sig.parameters[name].annotation is Path:
                bound.arguments[name] = Path(bound.arguments[name])
        return func(*bound.args, **bound.kwargs)

    return wrap

@_autopath
def show(pdf_path: Path) -> None:
    console = Console()
    with pdf_path.open("rb") as io:
        pdf = PdfFileReader(io)
        for i, pg in enumerate(pdf.pages):
            console.print(Panel(pg.extractText(), title=f"{i+1}"))


@_autopath
def copy_pages(source: Path, dest: Path, *indices: int):
    with source.open("rb") as s_io:
        s_pdf = PdfFileReader(s_io)
        w_pdf = PdfFileWriter()
        for i, pg in enumerate(s_pdf.pages):
            if i in indices:
                w_pdf.add_page(pg)
        with dest.open("wb") as d_io:
            w_pdf.write(d_io)


def merge(dest: Path, *pdf_paths: Path):
    w_pdf = PdfFileWriter()
    for pg in itertools.chain(
        *(getattr(p, "pages") for p in map(PdfFileReader, pdf_paths))
    ):
        w_pdf.addPage(pg)
    with dest.open("wb") as io:
        w_pdf.write(io)


def rotate_page(pdf_path: Path, index: int, angle, dest: Path | None = None):
    with pdf_path.open("rb") as s_io:
        r_pdf = PdfFileReader(s_io)
        w_pdf = PdfFileWriter()
        pages = [
            p if i != index else p.rotateClockwise(angle)
            for i, p in enumerate(r_pdf.pages)
        ]
        for i, p in enuerate(r_pdf.pages):
            if i != index:
                w_pdf.add_page(p)
            else:
                w_pdf.add_page(p.rotate_clockwise(angle))
        target = pdf_path if dest is None else dest

        with target.open("wb") as w_io:
            w_pdf.write(w_io)


