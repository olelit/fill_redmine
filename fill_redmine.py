import asyncio
from datetime import datetime

import requests

from configs.config import Config
from imports.import_factory import create_importer
from user_list import USERS


def format_created_on(created_on: str | None) -> str:
    if not created_on:
        return "unknown"

    try:
        created_at = datetime.fromisoformat(created_on.replace("Z", "+00:00"))
    except ValueError:
        return created_on

    return created_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def get_issue_info(issue_id: int, api_key: str) -> dict[str, str] | None:
    redmine_url = Config.get_redmine_base_url()
    if not redmine_url:
        return None

    normalized_redmine_url = redmine_url.rstrip("/")
    url = f"{normalized_redmine_url}/issues/{issue_id}.json"
    headers = {"X-Redmine-API-Key": api_key}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        issue = response.json().get("issue", {})
    except (requests.RequestException, ValueError) as exc:
        print(f"Warning: failed to fetch Redmine issue #{issue_id}: {exc}")
        return None

    author = issue.get("author") or {}
    return {
        "subject": issue.get("subject", "unknown"),
        "url": f"{normalized_redmine_url}/issues/{issue_id}",
        "author": author.get("name", "unknown"),
        "created_on": format_created_on(issue.get("created_on")),
    }


async def main():
    enabled_users = [u for u in USERS if u.is_enable]
    if not enabled_users:
        print("No enabled users found.")
        return

    print("\n" + "=" * 50)
    print("Time entries to be imported")
    print("=" * 50 + "\n")

    import_data = []
    issue_info_cache: dict[int, dict[str, str] | None] = {}

    for user in enabled_users:
        importer = create_importer(user)
        if not importer:
            continue

        records = importer.create_record_list()

        if not records:
            continue

        if user.issue_id not in issue_info_cache:
            issue_info_cache[user.issue_id] = get_issue_info(
                issue_id=user.issue_id,
                api_key=user.redmine_api_key,
            )

        issue_info = issue_info_cache[user.issue_id]

        print(f"=== User: {user.name} (user_id={user.user_id}) ===")
        print(f"Issue ID: {user.issue_id}")
        if issue_info:
            print(f"Issue: {issue_info['subject']}")
            print(f"Issue URL: {issue_info['url']}")
            print(f"Issue author: {issue_info['author']}")
            print(f"Issue created: {issue_info['created_on']}")
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
        await importer.handle()


if __name__ == "__main__":
    asyncio.run(main())
