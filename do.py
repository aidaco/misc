#! /bin/env python3

import glob
import subprocess
import sys

import typer

cli = typer.Typer()


def sh(*args):
    proc = subprocess.run(args, stdout=sys.stdout)
    return proc


@cli.command()
def test():
    sh("pytest", "-l", "--cov")


@cli.command()
def clean():
    sh("rm", "-rf", *glob.glob("**/__pycache__", recursive=True))
    sh("rm", "-rf", ".coverage")


@cli.command()
def fix():
    sh("black", ".")


if __name__ == "__main__":
    cli()
