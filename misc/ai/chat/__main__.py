import cyclopts
from misc.ai.chat import Chat

cli = cyclopts.App()


@cli.default()
def chat(system: str = "You are a helpful assistant."):
    chat = Chat(inplace=True).system(system)
    try:
        while True:
            chat.user(input(">"))
            print(chat.text())
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    cli()
