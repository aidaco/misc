import typer
import sys
import subprocess

cli = typer.Typer()


def sh(*args):
    proc = subprocess.run(args, stdout=sys.stdout)
    return proc


@cli.command()
def test():
    sh("pytest", "-l", "--cov")


if __name__ == "__main__":
    cli()
