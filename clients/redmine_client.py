import asyncio
import xml.etree.ElementTree as et
from collections.abc import Callable
from datetime import date

import aiohttp
import requests

from configs.config import Config
from dto.date_hours_dto import DateHoursDTO


class RedmineClient:
    PAGE_SIZE = 100

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = (Config.get_redmine_base_url() or "").rstrip("/")

    @staticmethod
    def print_progress(completed: int, total: int) -> None:
        bar_length = 20
        filled = bar_length if total == 0 else int(bar_length * completed / total)
        bar = "#" * filled + "-" * (bar_length - filled)
        print(f"\rProgress: [{bar}] {completed}/{total}", end="", flush=True)
        if completed == total:
            print()

    def get_issue(self, issue_id: int) -> dict | None:
        url = f"{self.base_url}/issues/{issue_id}.json"
        headers = {"X-Redmine-API-Key": self.api_key}

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json().get("issue", {})
        except (requests.RequestException, ValueError) as exc:
            print(f"Warning: failed to fetch Redmine issue #{issue_id}: {exc}")
            return None

    def get_time_entries(
        self, user_id: int, start: date, end: date
    ) -> list[dict]:
        url = f"{self.base_url}/time_entries.json"
        headers = {"X-Redmine-API-Key": self.api_key}
        entries: list[dict] = []
        offset = 0

        while True:
            params = {
                "user_id": user_id,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "limit": self.PAGE_SIZE,
                "offset": offset,
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("time_entries", [])
            entries.extend(batch)
            total = int(payload.get("total_count", len(entries)))
            if not batch or len(batch) < self.PAGE_SIZE or len(entries) >= total:
                break
            offset += self.PAGE_SIZE

        return entries

    def get_spent_on_dates(self, user_id: int, issue_id: int) -> set[str]:
        url = f"{self.base_url}/time_entries.xml"
        params = {
            "user_id": user_id,
            "issue_id": issue_id,
        }
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": self.api_key,
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        spent_on_dates: set[str] = set()
        try:
            root = et.fromstring(response.text)
            for entry in root.findall("time_entry"):
                spent_on = entry.find("spent_on")
                if spent_on is not None and spent_on.text:
                    spent_on_dates.add(spent_on.text)
        except et.ParseError as exc:
            print(f"XML parse error: {exc}")

        return spent_on_dates

    async def create_time_entries(
        self,
        user_id: int,
        issue_id: int,
        comment: str,
        activity_id: int,
        records: list[DateHoursDTO],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        url = f"{self.base_url}/time_entries.xml"
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            tasks = [
                asyncio.create_task(
                    self.create_time_entry(
                        session=session,
                        url=url,
                        headers=headers,
                        issue_id=issue_id,
                        user_id=user_id,
                        spent_on=record.date,
                        hours=record.hours,
                        activity_id=activity_id,
                        comment=comment,
                    )
                )
                for record in records
            ]

            total = len(tasks)
            if total == 0:
                return []

            errors: list[tuple[str, str]] = []
            completed = 0
            if on_progress is None:
                self.print_progress(completed=completed, total=total)

            for task in asyncio.as_completed(tasks):
                success, spent_on, error_message = await task
                completed += 1

                if not success:
                    if on_progress is None:
                        print()
                        print(f"ERROR: {spent_on} {error_message}")
                    errors.append((spent_on, error_message))

                if on_progress is not None:
                    on_progress(completed, total)
                else:
                    self.print_progress(completed=completed, total=total)

            return errors

    async def create_time_entry(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict[str, str],
        issue_id: int,
        user_id: int,
        spent_on: str,
        hours: int | float,
        activity_id: int,
        comment: str,
    ) -> tuple[bool, str, str | None]:
        body = f"""
    <time_entry>
      <issue_id>{issue_id}</issue_id>
      <user_id>{user_id}</user_id>
      <spent_on>{spent_on}</spent_on>
      <hours>{hours}</hours>
      <activity_id>{activity_id}</activity_id>
      <comments>{comment}</comments>
    </time_entry>
    """.strip()
        async with session.post(url, headers=headers, data=body) as response:
            text = await response.text()
            if 200 <= response.status < 300:
                return True, spent_on, None

            return False, spent_on, f"{response.status} {text}"
