import math
import re
from datetime import date, datetime
from pathlib import Path

from clients.git_client import GitClient, GitError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel

from mcp_server.config import (
    ProfileConfigError,
    UserProfile,
    load_users,
    select_user,
)
from mcp_server.plans import PlanStore, PlannedEntry, fingerprint_target_config
from mcp_server.tracker_access import build_user_tracker

ISSUE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
DEFAULT_DAILY_HOURS = 1.0
MAX_DAILY_HOURS = 8.0
HOURS_TOLERANCE = 1e-9


class YoutrackFillError(Exception):
    """Raised when a YouTrack fill request cannot be turned into a plan."""


class SuggestedEntry(BaseModel):
    date: str
    issue_id: str
    hours: float
    comment: str
    commit_hashes: list[str]


def register_youtrack_tools(
    server: MCPServer, users_path: Path, plans: PlanStore
) -> None:
    def prepare_youtrack_fill(
        user_name: str,
        repo_path: str,
        entries: list[SuggestedEntry],
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, object]:
        try:
            return _prepare_youtrack_fill(
                users_path, plans, user_name, repo_path, entries, start, end
            )
        except GitError:
            raise ToolError("Git commit read failed") from None
        except (ProfileConfigError, YoutrackFillError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(prepare_youtrack_fill, name="prepare_youtrack_fill")


def _prepare_youtrack_fill(
    users_path: Path,
    plans: PlanStore,
    user_name: str,
    repo_path: str,
    entries: list[SuggestedEntry],
    start: str | None,
    end: str | None,
) -> dict[str, object]:
    start_date, end_date = _period(start, end)
    profile = select_user(load_users(users_path), user_name)
    daily_issue, daily_hours = _daily_meeting_config(profile)
    tracker = build_user_tracker(profile, "youtrack")

    commits = GitClient(repo_path).list_commits(
        profile.git_email, start_date, end_date
    )
    commits_by_hash = _commits_by_hash(commits)
    if not commits_by_hash:
        raise YoutrackFillError("No commits found for the requested period")

    worklogs = tracker.get_worklogs(start_date, end_date)
    existing_by_date = _existing_hours_by_date(worklogs)
    existing_daily_dates = {
        item.date
        for item in worklogs
        if _normalize_issue(getattr(item, "issue", "")) == daily_issue
    }

    planned_entries, warnings = _validate_entries(
        entries,
        start_date,
        end_date,
        commits_by_hash,
        existing_by_date,
        existing_daily_dates,
        daily_issue,
        daily_hours,
    )

    plan = plans.create(
        user_name=profile.name,
        destination_kind="youtrack",
        issue_id="",
        entries=tuple(planned_entries),
        warnings=tuple(warnings),
        target_fingerprint=fingerprint_target_config(profile, "youtrack"),
    )
    return {
        "status": "plan_created",
        "plan_id": plan.plan_id,
        "user": plan.user_name,
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "entries": [
            {
                "date": entry.date,
                "issue": entry.issue_id,
                "hours": entry.hours,
                "comment": entry.comment,
                "commit_hashes": list(entry.commit_hashes),
            }
            for entry in plan.entries
        ],
        "warnings": list(plan.warnings),
    }


def _validate_entries(
    entries: list[SuggestedEntry],
    start_date: date,
    end_date: date,
    commits_by_hash: dict[str, tuple[object, date]],
    existing_by_date: dict[str, float],
    existing_daily_dates: set[str],
    daily_issue: str | None,
    daily_hours: float,
) -> tuple[list[PlannedEntry], list[str]]:
    if not entries:
        raise YoutrackFillError("At least one entry is required")

    planned: list[PlannedEntry] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    proposed_by_date: dict[str, float] = {}

    for entry in entries:
        entry_date = _entry_date(entry.date, start_date, end_date)
        day = entry_date.isoformat()
        issue = _entry_issue(entry.issue_id)
        hours = _entry_hours(day, entry.hours)
        comment = _entry_comment(day, entry.comment)
        hashes = tuple(
            commit_hash.strip() for commit_hash in entry.commit_hashes
        )

        key = (day, issue)
        if key in seen:
            raise YoutrackFillError(f"{day}: duplicate date and issue {issue}")
        seen.add(key)

        if not hashes:
            _validate_daily_meeting(
                day,
                entry_date,
                issue,
                hours,
                daily_issue,
                daily_hours,
                existing_daily_dates,
            )
        else:
            referenced = _validate_commit_hashes(
                day, hashes, commits_by_hash
            )
            if not _mentions_issue(referenced, issue):
                warnings.append(
                    f"{day}: issue {issue} not found in commit subjects"
                )

        planned.append(
            PlannedEntry(
                date=day,
                hours=hours,
                comment=comment,
                commit_hashes=hashes,
                issue_id=issue,
            )
        )
        proposed_by_date[day] = proposed_by_date.get(day, 0.0) + hours

    for day, proposed in proposed_by_date.items():
        existing = existing_by_date.get(day, 0.0)
        if proposed + existing > MAX_DAILY_HOURS + HOURS_TOLERANCE:
            raise YoutrackFillError(
                f"{day}: proposed hours exceed the "
                f"{MAX_DAILY_HOURS:g}-hour daily limit"
            )

    return planned, warnings


def _validate_daily_meeting(
    day: str,
    entry_date: date,
    issue: str,
    hours: float,
    daily_issue: str | None,
    daily_hours: float,
    existing_daily_dates: set[str],
) -> None:
    if daily_issue is None:
        raise YoutrackFillError(
            f"{day}: daily meeting is not configured; commit hashes are required"
        )
    if issue != daily_issue:
        raise YoutrackFillError(
            f"{day}: commit hashes are required for issue {issue}"
        )
    if abs(hours - daily_hours) > HOURS_TOLERANCE:
        raise YoutrackFillError(
            f"{day}: daily meeting hours must match the configured "
            f"{daily_hours:g}"
        )
    if entry_date.weekday() >= 5:
        raise YoutrackFillError(
            f"{day}: daily meeting is only allowed on working days"
        )
    if day in existing_daily_dates:
        raise YoutrackFillError(f"{day}: daily meeting is already recorded")


def _validate_commit_hashes(
    day: str,
    hashes: tuple[str, ...],
    commits_by_hash: dict[str, tuple[object, date]],
) -> list[object]:
    referenced = []
    for commit_hash in hashes:
        commit = commits_by_hash.get(commit_hash)
        if commit is None:
            raise YoutrackFillError(f"{day}: unknown commit {commit_hash}")
        commit_object, commit_date = commit
        if commit_date.isoformat() != day:
            raise YoutrackFillError(
                f"{day}: commit {commit_hash} belongs to "
                f"{commit_date.isoformat()}"
            )
        referenced.append(commit_object)
    return referenced


def _mentions_issue(commits: list[object], issue: str) -> bool:
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(issue)}(?!\d)")
    for commit in commits:
        text = f"{commit.subject}\n{commit.body}".upper()
        if pattern.search(text):
            return True
    return False


def _entry_date(raw: str, start_date: date, end_date: date) -> date:
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise YoutrackFillError(
            f"{raw!r}: date must use YYYY-MM-DD ISO format"
        ) from None
    if value.isoformat() != raw:
        raise YoutrackFillError(f"{raw!r}: date must use YYYY-MM-DD ISO format")
    if not start_date <= value <= end_date:
        raise YoutrackFillError(
            f"{value.isoformat()}: date is outside the requested period"
        )
    return value


def _entry_issue(raw: str) -> str:
    issue = raw.strip().upper()
    if not ISSUE_PATTERN.fullmatch(issue):
        raise YoutrackFillError(f"Invalid issue ID: {raw!r}")
    return issue


def _entry_hours(day: str, raw: float) -> float:
    hours = float(raw)
    if not math.isfinite(hours) or hours <= 0:
        raise YoutrackFillError(
            f"{day}: hours must be positive and a multiple of 0.5"
        )
    doubled = hours * 2
    if abs(doubled - round(doubled)) > HOURS_TOLERANCE:
        raise YoutrackFillError(
            f"{day}: hours must be positive and a multiple of 0.5"
        )
    return hours


def _entry_comment(day: str, raw: str) -> str:
    comment = raw.strip()
    if not comment:
        raise YoutrackFillError(f"{day}: comment is required")
    return comment


def _daily_meeting_config(
    profile: UserProfile,
) -> tuple[str | None, float]:
    raw_issue = profile.youtrack.get("daily_meeting_issue_id")
    if raw_issue is None or (
        isinstance(raw_issue, str) and not raw_issue.strip()
    ):
        return None, DEFAULT_DAILY_HOURS
    if not isinstance(raw_issue, str):
        raise ProfileConfigError("Daily meeting issue ID is invalid")
    daily_issue = raw_issue.strip().upper()
    if not ISSUE_PATTERN.fullmatch(daily_issue):
        raise ProfileConfigError("Daily meeting issue ID is invalid")

    raw_hours = profile.youtrack.get("daily_meeting_hours", DEFAULT_DAILY_HOURS)
    if isinstance(raw_hours, bool) or not isinstance(raw_hours, (int, float)):
        raise ProfileConfigError("Daily meeting hours are invalid")
    daily_hours = float(raw_hours)
    if not math.isfinite(daily_hours) or daily_hours <= 0:
        raise ProfileConfigError("Daily meeting hours are invalid")
    return daily_issue, daily_hours


def _commits_by_hash(commits) -> dict[str, tuple[object, date]]:
    by_hash: dict[str, tuple[object, date]] = {}
    for commit in commits:
        commit_date = _commit_date(commit)
        if commit_date is None:
            continue
        by_hash.setdefault(commit.hash, (commit, commit_date))
    return by_hash


def _commit_date(commit) -> date | None:
    raw = commit.date
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return datetime.fromisoformat(raw).date()
    except (TypeError, ValueError):
        return None


def _existing_hours_by_date(worklogs) -> dict[str, float]:
    by_date: dict[str, float] = {}
    for item in worklogs:
        by_date[item.date] = by_date.get(item.date, 0.0) + float(item.hours)
    return by_date


def _normalize_issue(raw: object) -> str:
    return raw.strip().upper() if isinstance(raw, str) else ""


def _default_period(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def _period(
    start: str | None, end: str | None, today: date | None = None
) -> tuple[date, date]:
    today = today if today is not None else date.today()
    default_start, default_end = _default_period(today)
    start_date = _period_date(start) if start is not None else default_start
    end_date = _period_date(end) if end is not None else default_end
    if start_date > end_date:
        raise YoutrackFillError("Start date must not be after end date")
    return start_date, end_date


def _period_date(raw: str) -> date:
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise YoutrackFillError(
            "Dates must use YYYY-MM-DD ISO format"
        ) from None
    if value.isoformat() != raw:
        raise YoutrackFillError("Dates must use YYYY-MM-DD ISO format")
    return value