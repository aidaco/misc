import cyclopts

from .filer_cli import cli as filer

cli = cyclopts.App()
cli.command(filer, name=["filer", "f"])
