import cyclopts

from wg.world import explore
from wg.state import stateful

app = cyclopts.App()


@app.command()
def go():
    explore()


@app.command()
def state():
    stateful()
