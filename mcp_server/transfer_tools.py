import math
from datetime import date
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.config import ProfileConfigError, load_users, select_user
from mcp_server.periods import PeriodError, parse_period
from mcp_server.plans import (
    PlanStore,
    PlannedDeletion,
    PlannedEntry,
    fingerprint_target_config,
)
from mcp_server.tracker_access import (
    build_user_tracker,
    required_redmine_comment,
)
from trackers.base import BaseTracker

MAX_DAILY_HOURS = 8.0
HOURS_TOLERANCE = 1e-9


class RedmineTransferError(Exception):
    """Raised when a YouTrack to Redmine transfer cannot be planned."""


def register_transfer_tools(
    server: MCPServer, users_path: Path, plans: PlanStore
) -> None:
    def prepare_youtrack_transfer(
        user_name: str,
        issue_id: int,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, object]:
        try:
            return _prepare_youtrack_transfer(
                users_path, plans, user_name, issue_id, start, end
            )
        except (
            ProfileConfigError,
            PeriodError,
            RedmineTransferError,
            ValueError,
        ) as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(
        prepare_youtrack_transfer, name="prepare_youtrack_transfer"
    )


def _prepare_youtrack_transfer(
    users_path: Path,
    plans: PlanStore,
    user_name: str,
    issue_id: int,
    start: str | None,
    end: str | None,
) -> dict[str, object]:
    target_issue = _target_issue(issue_id)
    start_date, end_date = parse_period(start, end)
    profile = select_user(load_users(users_path), user_name)
    comment = required_redmine_comment(profile)
    source = build_user_tracker(profile, "youtrack")
    destination = build_user_tracker(profile, "redmine")
    worklogs = source.get_worklogs(start_date, end_date)
    if not worklogs:
        raise RedmineTransferError(
            "No YouTrack worklogs found for the requested period"
        )

    totals, source_issues = _aggregate(worklogs)
    existing_by_date = _entries_by_date(
        _redmine_entries(destination, start_date, end_date)
    )
    entries: list[PlannedEntry] = []
    deletions: list[PlannedDeletion] = []
    warnings: list[str] = []
    for day in sorted(totals):
        hours = totals[day]
        if hours > MAX_DAILY_HOURS + HOURS_TOLERANCE:
            warnings.append(
                f"{day}: YouTrack hours {hours:g} exceed "
                f"{MAX_DAILY_HOURS:g}"
            )
        entries.append(
            PlannedEntry(
                date=day,
                hours=hours,
                comment=comment,
                commit_hashes=(),
                issue_id=str(target_issue),
            )
        )
        for raw_entry in existing_by_date.get(day, []):
            deletions.append(_deletion(day, raw_entry))

    plan = plans.create(
        user_name=profile.name,
        destination_kind="redmine",
        issue_id=str(target_issue),
        entries=tuple(entries),
        warnings=tuple(warnings),
        target_fingerprint=fingerprint_target_config(profile, "redmine"),
        deletions=tuple(deletions),
    )
    return {
        "status": "plan_created",
        "plan_id": plan.plan_id,
        "user": plan.user_name,
        "destination": {"tracker": "redmine", "issue": target_issue},
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "entries": [
            {
                "date": entry.date,
                "issue": target_issue,
                "hours": entry.hours,
                "comment": entry.comment,
                "source_issues": sorted(
                    source_issues.get(entry.date, set())
                ),
                "replaces": [
                    {"id": deletion.entry_id, "hours": deletion.hours}
                    for deletion in plan.deletions
                    if deletion.date == entry.date
                ],
            }
            for entry in plan.entries
        ],
        "warnings": list(plan.warnings),
    }


def _target_issue(raw: int) -> int:
    if isinstance(raw, bool):
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        )
    try:
        issue = int(raw)
    except (TypeError, ValueError):
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        ) from None
    if issue <= 0:
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        )
    return issue


def _aggregate(
    worklogs: list,
) -> tuple[dict[str, float], dict[str, set[str]]]:
    totals: dict[str, float] = {}
    issues: dict[str, set[str]] = {}
    for item in worklogs:
        day = item.date
        if not isinstance(day, str) or not day:
            raise RedmineTransferError("YouTrack worklog has no date")
        try:
            hours = float(item.hours)
        except (TypeError, ValueError):
            raise RedmineTransferError(
                f"{day}: invalid YouTrack hours"
            ) from None
        if not math.isfinite(hours) or hours <= 0:
            raise RedmineTransferError(f"{day}: invalid YouTrack hours")
        totals[day] = round(totals.get(day, 0.0) + hours, 2)
        issue = item.issue.strip() if isinstance(item.issue, str) else ""
        if issue:
            issues.setdefault(day, set()).add(issue)
    return totals, issues


def _redmine_entries(
    tracker: BaseTracker, start_date: date, end_date: date
) -> list[dict]:
    getter = getattr(tracker, "get_time_entries", None)
    if getter is None:
        raise RedmineTransferError(
            "Redmine tracker cannot read time entry IDs"
        )
    return getter(start_date, end_date)


def _entries_by_date(entries: list[dict]) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = {}
    for entry in entries:
        day = entry.get("spent_on")
        if not isinstance(day, str) or not day:
            raise RedmineTransferError(
                "Redmine time entry has no spent_on date"
            )
        by_date.setdefault(day, []).append(entry)
    return by_date


def _deletion(day: str, entry: dict) -> PlannedDeletion:
    entry_id = entry.get("id")
    if (
        isinstance(entry_id, bool)
        or not isinstance(entry_id, int)
        or entry_id <= 0
    ):
        raise RedmineTransferError(
            f"{day}: Redmine time entry ID is missing"
        )
    try:
        hours = float(entry.get("hours", 0))
    except (TypeError, ValueError):
        raise RedmineTransferError(
            f"{day}: invalid Redmine hours"
        ) from None
    if not math.isfinite(hours) or hours < 0:
        raise RedmineTransferError(f"{day}: invalid Redmine hours")
    return PlannedDeletion(date=day, entry_id=entry_id, hours=hours)