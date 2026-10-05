import argparse
import asyncio

from services.import_service import ImportService
from services.preview_service import PreviewService
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository


async def main(
    override_issue_id: int | None = None,
    repo: UserRepository | None = None,
) -> None:
    repository = repo if repo is not None else UserRepository()
    users = repository.list_users()
    enabled_users = [user for user in users if user.is_enable]
    if not enabled_users:
        print("No enabled users found.")
        return

    if override_issue_id:
        for user in enabled_users:
            user.issue_id = override_issue_id

    PreviewService.print_header()

    service = ImportService()
    items = service.prepare(enabled_users)

    for item in items:
        PreviewService.print_preview(item.preview)

    if not items:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")

    summary = await service.run(items)
    print(f"Import finished: {summary.total} entries, {len(summary.errors)} errors.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Override issue ID for all users")
    args = parser.parse_args()

    repository = UserRepository()
    migrate_from_user_list(repository)
    asyncio.run(main(override_issue_id=args.id, repo=repository))
