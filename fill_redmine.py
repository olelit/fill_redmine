import asyncio

from configs.users import USERS
from imports.import_factory import create_importer


async def main():
    for user in USERS:
        if not user.is_enable:
            continue

        importer = create_importer(user)
        if importer:
            await importer.run()


if __name__ == "__main__":
    asyncio.run(main())
