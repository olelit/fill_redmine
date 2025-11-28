import asyncio
import os
from dotenv import load_dotenv
from imports.import_factory import create_importer


async def main():
    i: int = 1

    while True:
        source = os.getenv(f"SOURCE_{i}")
        if source is None:
            print('End of source. Exiting.')
            break

        importer = create_importer(i)
        await importer.run()
        i += 1

    pass


if __name__ == "__main__":
    asyncio.run(main())
