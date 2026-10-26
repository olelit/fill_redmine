from datetime import date

from clients.redmine_client import RedmineClient
from dto.worklog_dto import WorklogDTO
from trackers.base import BaseTracker, TrackerField
from trackers.registry import register_tracker


@register_tracker
class RedmineTracker(BaseTracker):
    kind = "redmine"
    label = "Redmine"
    can_write = True
    fields = (
        TrackerField("api_key", "API key", kind="secret"),
        TrackerField("user_id", "user_id", kind="int"),
        TrackerField("activity_id", "activity_id", kind="int"),
        TrackerField("issue_id", "issue_id", kind="int"),
        TrackerField("comment", "Комментарий", kind="textarea", required=False),
    )

    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        client = RedmineClient(api_key=self.config["api_key"])
        entries = client.get_time_entries(
            user_id=int(self.config["user_id"]),
            start=start,
            end=end,
        )
        result: list[WorklogDTO] = []
        for entry in entries:
            issue = entry.get("issue") or {}
            result.append(
                WorklogDTO(
                    date=entry["spent_on"],
                    hours=float(entry.get("hours", 0)),
                    description=entry.get("comments", ""),
                    issue=str(issue.get("id", "")),
                    source=self.kind,
                )
            )
        return result
