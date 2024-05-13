import subprocess
import os
import sys


def upgrade_and_restart():
    upgrade_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "/mnt/c/Users/btlab/Downloads/reload",
    ]
    subprocess.run(upgrade_command, check=True, capture_output=True)
    print("Upgraded, restarting.")

    argv = [sys.executable, *(arg for arg in sys.argv if arg != "reload")]
    os.execv(argv[0], argv)


def main():
    global print
    if "-c" in sys.argv:
        import rich
        import rich.console

        def print(*args):
            rich.print(f"[red]{args}[/]")

    print(*sys.argv)
    if "reload" in sys.argv:
        print("Upgrade required.")
        upgrade_and_restart()


if __name__ == "__main__":
    main()
