import sys

from work_assistant_cli import cli, main


if __name__ == "__main__":
    print(
        "fill_redmine.py переименован в work_assistant_cli.py",
        file=sys.stderr,
    )
    cli()
