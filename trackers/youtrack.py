from datetime import date, datetime, timezone

from clients.youtrack_client import YoutrackClient
from dto.worklog_dto import WorklogDTO
from trackers.base import BaseTracker
from trackers.registry import register_tracker


@register_tracker
class YoutrackTracker(BaseTracker):
    kind = "youtrack"
    label = "YouTrack"
    can_write = True

    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        client = YoutrackClient(access_token=self.config["access_token"])
        items = client.get_work_items(
            start_date=datetime.combine(start, datetime.min.time()),
            end_date=datetime.combine(end, datetime.max.time()),
        )
        by_key: dict[tuple[str, str], float] = {}
        for item in items:
            item_date = (
                datetime.fromtimestamp(item["date"] / 1000, tz=timezone.utc)
                .date()
                .isoformat()
            )
            issue = (item.get("issue") or {}).get("idReadable") or ""
            minutes = float((item.get("duration") or {}).get("minutes", 0))
            by_key[(item_date, issue)] = by_key.get((item_date, issue), 0) + minutes / 60

        return [
            WorklogDTO(date=item_date, hours=hours, issue=issue, source=self.kind)
            for (item_date, issue), hours in sorted(by_key.items())
        ]

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        issue_id = str(self.config.get("issue_id", "")).strip()
        if not issue_id:
            raise ValueError("YouTrack не настроен: issue_id")
        client = YoutrackClient(access_token=self.config["access_token"])
        return client.create_work_items(issue_id, records)
