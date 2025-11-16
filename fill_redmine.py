import asyncio

from imports.import_factory import create_importer


async def main():
    i: int = 1
    while True:
        importer = create_importer(i)
        await importer.run()
        i+=1
        break

    pass


if __name__ == "__main__":
    asyncio.run(main())
