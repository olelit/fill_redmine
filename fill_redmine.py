import argparse
import asyncio

from imports.import_factory import create_importer
from services.preview_service import PreviewService
from user_list import USERS


async def main(override_issue_id: int | None = None):
    enabled_users = [u for u in USERS if u.is_enable]
    if not enabled_users:
        print("No enabled users found.")
        return

    if override_issue_id:
        for u in enabled_users:
            u.issue_id = override_issue_id

    PreviewService.print_header()

    import_data = []
    issue_info_cache = {}

    for user in enabled_users:
        importer = create_importer(user)
        if not importer:
            continue

        records = importer.create_record_list()

        if not records:
            continue

        issue_info = PreviewService.get_issue_info(
            issue_info_cache=issue_info_cache,
            user=user,
        )
        PreviewService.print_user_preview(
            user=user,
            records=records,
            issue_info=issue_info,
        )

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
        await importer.handle()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Override issue ID for all users")
    args = parser.parse_args()
    asyncio.run(main(override_issue_id=args.id))
