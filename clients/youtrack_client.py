from datetime import date, datetime, timezone
from urllib.parse import quote

import requests

from configs.config import Config
from dto.worklog_dto import WorklogDTO


def _utc_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


class YoutrackClient:
    PAGE_SIZE = 100

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = (Config.get_youtrack_base_url() or "").rstrip("/")

    def get_work_items(self, start_date: datetime, end_date: datetime) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/api/workItems"
        items: list[dict] = []
        skip = 0

        while True:
            params = {
                "fields": "id,date,duration(minutes),text,issue(idReadable)",
                "start": int(_utc_ms(start_date)),
                "end": int(_utc_ms(end_date)),
                "$top": self.PAGE_SIZE,
                "$skip": skip,
                "author": "me",
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            items.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            skip += self.PAGE_SIZE

        return items

    def create_work_items(
        self, issue_id: str, records: list[WorklogDTO]
    ) -> list[tuple[str, str]]:
        quoted_issue_id = quote(issue_id, safe="")
        url = f"{self.base_url}/api/issues/{quoted_issue_id}/timeTracking/workItems"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        errors: list[tuple[str, str]] = []
        for record in records:
            try:
                day = date.fromisoformat(record.date)
            except ValueError:
                errors.append((record.date, "invalid date"))
                continue

            start_ms = int(
                datetime.combine(
                    day, datetime.min.time(), tzinfo=timezone.utc
                ).timestamp()
                * 1000
            )
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json={
                        "date": start_ms,
                        "duration": {"minutes": int(round(record.hours * 60))},
                        "text": record.description or "development",
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
