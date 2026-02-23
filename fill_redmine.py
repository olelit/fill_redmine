import asyncio

from configs.users import USERS
from imports.import_factory import create_importer


async def main():
    enabled_users = [u for u in USERS if u.is_enable]
    if not enabled_users:
        print("No enabled users found.")
        return

    print("\n" + "=" * 50)
    print("Time entries to be imported")
    print("=" * 50 + "\n")

    import_data = []

    for user in enabled_users:
        importer = create_importer(user)
        if not importer:
            continue

        records = importer.create_record_list()

        if not records:
            continue

        print(f"=== User: {user.name} (user_id={user.user_id}) ===")
        print(f"Driver: {user.driver}")
        print(f"Comment: {user.comment}")
        print("Dates:")

        total_hours = 0
        for record in records:
            print(f"  {record.date} - {record.hours}h")
            total_hours += record.hours

        print(f"Total hours: {total_hours}h")
        print()

        import_data.append((importer, records))

    if not import_data:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")

    for importer, records in import_data:
        await importer.run()


if __name__ == "__main__":
    asyncio.run(main())
