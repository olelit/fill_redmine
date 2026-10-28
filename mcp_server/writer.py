from pathlib import Path

from dto.worklog_dto import WorklogDTO
from mcp_server.config import ProfileConfigError, load_users, select_user
from mcp_server.plans import WritePlan
from mcp_server.tracker_access import build_user_tracker


def execute_plan(plan: WritePlan, users_path: Path) -> dict[str, object]:
    if plan.destination_kind not in ("redmine", "youtrack"):
        raise ProfileConfigError("Unsupported tracker kind")

    profile = select_user(load_users(users_path), plan.user_name)
    if plan.destination_kind == "redmine":
        issue_id = _redmine_issue_id(plan.issue_id)
        tracker = build_user_tracker(
            profile,
            "redmine",
            issue_id=issue_id,
            for_write=True,
        )
    else:
        current_issue_id = str(profile.youtrack.get("issue_id") or "").strip()
        if current_issue_id != plan.issue_id:
            raise ProfileConfigError("YouTrack issue changed since plan creation")
        tracker = build_user_tracker(profile, "youtrack", for_write=True)

    records = [
        WorklogDTO(
            date=entry.date,
            hours=entry.hours,
            description=entry.comment,
            issue=plan.issue_id,
            source=plan.destination_kind,
        )
        for entry in plan.entries
    ]
    failures = tracker.create_worklogs(records)
    failed_dates = {entry_date for entry_date, _message in failures}
    return {
        "results": [
            {
                "date": entry.date,
                "status": "failed" if entry.date in failed_dates else "created",
            }
            for entry in plan.entries
        ]
    }


def _redmine_issue_id(raw_issue_id: str) -> int:
    try:
        issue_id = int(raw_issue_id)
    except (TypeError, ValueError):
        raise ProfileConfigError("Redmine write requires a valid issue ID") from None
    if issue_id <= 0:
        raise ProfileConfigError("Redmine write requires a valid issue ID")
    return issue_id
