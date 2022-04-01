import typer
import sys
import subprocess
import glob

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
    sh("black", ".", "--target-version", "py310")


if __name__ == "__main__":
    cli()
