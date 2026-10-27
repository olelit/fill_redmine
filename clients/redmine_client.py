from datetime import date

import requests

from configs.config import Config
from dto.worklog_dto import WorklogDTO


class RedmineClient:
    PAGE_SIZE = 100

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = (Config.get_redmine_base_url() or "").rstrip("/")

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

    def create_time_entries_sync(
        self,
        user_id: int,
        issue_id: int,
        activity_id: int,
        records: list[WorklogDTO],
    ) -> list[tuple[str, str]]:
        url = f"{self.base_url}/time_entries.json"
        headers = {"X-Redmine-API-Key": self.api_key}
        errors: list[tuple[str, str]] = []
        for record in records:
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json={
                        "time_entry": {
                            "issue_id": issue_id,
                            "user_id": user_id,
                            "spent_on": record.date,
                            "hours": record.hours,
                            "activity_id": activity_id,
                            "comments": record.description or "development",
                        }
                    },
                    timeout=10,
                )
            except requests.RequestException as exc:
                errors.append((record.date, str(exc)))
                continue

            if not 200 <= response.status_code < 300:
                errors.append(
                    (record.date, f"{response.status_code} {response.text[:200]}")
                )
        return errors
