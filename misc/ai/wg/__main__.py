import cyclopts

from wg.world import explore
from wg.state import stateful

cli = cyclopts.App()


@cli.command()
def go():
    explore()


@cli.command()
def state():
    stateful()


if __name__ == "__main__":
    cli()
