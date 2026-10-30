import math
import re
from datetime import date, time, timedelta
from pathlib import Path

from clients.git_client import GitClient, GitError
from dto.git_commit_dto import GitCommitDTO
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.commit_allocation import (
    COMMENT_LIMIT,
    DEFAULT_COMMENT,
    DEFAULT_WORKDAY_START,
    allocate_commit_hours,
)
from mcp_server.config import (
    ProfileConfigError,
    UserProfile,
    load_users,
    select_user,
)
from mcp_server.periods import PeriodError, parse_period
from mcp_server.plans import PlanStore, PlannedEntry, fingerprint_target_config
from mcp_server.tracker_access import build_user_tracker
from mcp_server.youtrack_tools import (
    HOURS_TOLERANCE,
    MAX_DAILY_HOURS,
    YoutrackFillError,
    _commit_date,
    _daily_meeting_config,
    _existing_hours_by_date,
    _fallback_issue,
    _normalize_issue,
)

DEFAULT_DAILY_HOURS = 8.0
WORKDAY_START_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
PROJECT_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9]+")

TOOL_DESCRIPTION = (
    "Готовит план списания времени в YouTrack по git-коммитам профиля. "
    "По умолчанию берёт только сегодняшний день и 8 часов; часы распределяются "
    "пропорционально интервалам между коммитами начиная с youtrack.workday_start. "
    "Уже списанные часы учитываются, дейли-митинг добавляется автоматически. "
    "Ничего не записывает: план живёт в памяти, для записи вызовите write_plan "
    "с полученным plan_id."
)


def register_commit_tools(
    server: MCPServer, users_path: Path, plans: PlanStore
) -> None:
    def prepare_youtrack_from_commits(
        user_name: str,
        repo_path: str,
        start: str | None = None,
        end: str | None = None,
        daily_hours: float = DEFAULT_DAILY_HOURS,
    ) -> dict[str, object]:
        try:
            return _prepare_youtrack_from_commits(
                users_path,
                plans,
                user_name,
                repo_path,
                start,
                end,
                daily_hours,
            )
        except GitError:
            raise ToolError("Git commit read failed") from None
        except (
            ProfileConfigError,
            PeriodError,
            YoutrackFillError,
            ValueError,
        ) as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(
        prepare_youtrack_from_commits,
        name="prepare_youtrack_from_commits",
        description=TOOL_DESCRIPTION,
    )


def _prepare_youtrack_from_commits(
    users_path: Path,
    plans: PlanStore,
    user_name: str,
    repo_path: str,
    start: str | None,
    end: str | None,
    daily_hours: float,
) -> dict[str, object]:
    target_hours = _target_hours(daily_hours)
    start_date, end_date = _period(start, end)
    profile = select_user(load_users(users_path), user_name)
    daily_issue, meeting_hours = _daily_meeting_config(profile)
    fallback_issue = _fallback_issue(profile)
    default_comment = _default_comment(profile)
    workday_start = _workday_start(profile)
    project_keys = _project_keys(profile, daily_issue, fallback_issue)

    tracker = build_user_tracker(profile, "youtrack")
    worklogs = tracker.get_worklogs(start_date, end_date)
    existing_by_date = _existing_hours_by_date(worklogs)
    existing_daily_dates = {
        item.date
        for item in worklogs
        if _normalize_issue(getattr(item, "issue", "")) == daily_issue
    }

    commits = GitClient(repo_path).list_commits(
        profile.git_email, start_date, end_date
    )
    commits_by_date = _commits_by_date(commits, start_date, end_date)

    entries, warnings = _plan_days(
        start_date,
        end_date,
        commits_by_date,
        existing_by_date,
        existing_daily_dates,
        daily_issue,
        meeting_hours,
        fallback_issue,
        default_comment,
        workday_start,
        target_hours,
        project_keys,
    )
    merged = _merge_entries(entries)
    if not merged:
        raise YoutrackFillError(_no_entries_message(warnings))

    plan = plans.create(
        user_name=profile.name,
        destination_kind="youtrack",
        issue_id="",
        entries=tuple(merged),
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
        "daily_hours": target_hours,
    }


def _plan_days(
    start_date: date,
    end_date: date,
    commits_by_date: dict[date, list[GitCommitDTO]],
    existing_by_date: dict[str, float],
    existing_daily_dates: set[str],
    daily_issue: str | None,
    meeting_hours: float,
    fallback_issue: str | None,
    default_comment: str,
    workday_start: time,
    target_hours: float,
    project_keys: tuple[str, ...],
) -> tuple[list[PlannedEntry], list[str]]:
    entries: list[PlannedEntry] = []
    warnings: list[str] = []
    day = start_date
    while day <= end_date:
        key = day.isoformat()
        existing = existing_by_date.get(key, 0.0)
        raw_remaining = target_hours - existing
        if raw_remaining <= HOURS_TOLERANCE:
            warnings.append(f"{key}: already has {existing:g} hours; skipped")
            day += timedelta(days=1)
            continue

        remaining = _quantize(raw_remaining)
        lost = raw_remaining - remaining
        if lost > HOURS_TOLERANCE:
            warnings.append(
                f"{key}: {lost:g} h cannot be planned in half-hour units"
            )

        meeting_due = (
            daily_issue is not None
            and day.weekday() < 5
            and key not in existing_daily_dates
        )
        if meeting_due:
            if remaining >= meeting_hours - HOURS_TOLERANCE:
                entries.append(
                    PlannedEntry(
                        date=key,
                        hours=meeting_hours,
                        comment="Daily meeting",
                        commit_hashes=(),
                        issue_id=daily_issue,
                    )
                )
                remaining = _quantize(remaining - meeting_hours)
            else:
                warnings.append(
                    f"{key}: not enough room for the daily meeting"
                )

        if remaining < 0.5 - HOURS_TOLERANCE:
            warnings.append(f"{key}: less than 0.5 hours left; skipped")
            day += timedelta(days=1)
            continue

        day_commits = commits_by_date.get(day, [])
        if day_commits:
            entries.extend(
                _entries_from_commits(
                    key,
                    day,
                    day_commits,
                    remaining,
                    workday_start,
                    fallback_issue,
                    default_comment,
                    warnings,
                    project_keys,
                )
            )
        else:
            _add_fallback(
                entries,
                warnings,
                key,
                remaining,
                (),
                fallback_issue,
                default_comment,
                reason="no commits",
            )
        day += timedelta(days=1)
    return entries, warnings


def _quantize(hours: float) -> float:
    return math.floor(hours * 2 + HOURS_TOLERANCE) / 2


def _entries_from_commits(
    key: str,
    day: date,
    day_commits: list[GitCommitDTO],
    remaining: float,
    workday_start: time,
    fallback_issue: str | None,
    default_comment: str,
    warnings: list[str],
    project_keys: tuple[str, ...],
) -> list[PlannedEntry]:
    result = allocate_commit_hours(
        day_commits,
        day=day,
        hours=remaining,
        workday_start=workday_start,
        fallback_issue=fallback_issue,
        fallback_comment=default_comment,
        project_keys=project_keys,
    )
    warnings.extend(result.warnings)
    if result.allocations:
        return [
            PlannedEntry(
                date=key,
                hours=allocation.hours,
                comment=allocation.comment,
                commit_hashes=allocation.commit_hashes,
                issue_id=allocation.issue,
            )
            for allocation in result.allocations
        ]

    entries: list[PlannedEntry] = []
    hashes = tuple(commit.hash for commit in day_commits)
    _add_fallback(
        entries,
        warnings,
        key,
        remaining,
        hashes,
        fallback_issue,
        default_comment,
        reason="no issue references in commits",
    )
    return entries


def _add_fallback(
    entries: list[PlannedEntry],
    warnings: list[str],
    key: str,
    hours: float,
    commit_hashes: tuple[str, ...],
    fallback_issue: str | None,
    default_comment: str,
    *,
    reason: str,
) -> None:
    if fallback_issue is None:
        warnings.append(
            f"{key}: {reason} and no fallback issue configured; skipped"
        )
        return
    entries.append(
        PlannedEntry(
            date=key,
            hours=hours,
            comment=default_comment,
            commit_hashes=commit_hashes,
            issue_id=fallback_issue,
        )
    )
    warnings.append(f"{key}: {reason}; filled on fallback issue {fallback_issue}")


def _merge_entries(entries: list[PlannedEntry]) -> list[PlannedEntry]:
    hours: dict[tuple[str, str], float] = {}
    comments: dict[tuple[str, str], list[str]] = {}
    hashes: dict[tuple[str, str], list[str]] = {}
    order: list[tuple[str, str]] = []

    for entry in entries:
        key = (entry.date, entry.issue_id)
        if key not in hours:
            hours[key] = 0.0
            comments[key] = []
            hashes[key] = []
            order.append(key)
        hours[key] += entry.hours
        if entry.comment not in comments[key]:
            comments[key].append(entry.comment)
        for commit_hash in entry.commit_hashes:
            if commit_hash not in hashes[key]:
                hashes[key].append(commit_hash)

    return [
        PlannedEntry(
            date=key[0],
            hours=round(hours[key], 2),
            comment="; ".join(comments[key])[:COMMENT_LIMIT],
            commit_hashes=tuple(hashes[key]),
            issue_id=key[1],
        )
        for key in order
    ]


def _commits_by_date(
    commits: list[GitCommitDTO], start_date: date, end_date: date
) -> dict[date, list[GitCommitDTO]]:
    by_date: dict[date, list[GitCommitDTO]] = {}
    for commit in commits:
        commit_date = _commit_date(commit)
        if commit_date is None or not start_date <= commit_date <= end_date:
            continue
        by_date.setdefault(commit_date, []).append(commit)
    return by_date


def _period(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if start is None and end is not None:
        start_date, end_date = parse_period(end, end)
    else:
        start_date, end_date = parse_period(
            start if start is not None else today.isoformat(),
            end if end is not None else today.isoformat(),
        )
    if end_date > today:
        raise PeriodError("End date must not be in the future")
    return start_date, end_date


def _target_hours(raw: float) -> float:
    message = (
        f"daily_hours must be greater than 0 and not more than {MAX_DAILY_HOURS:g}"
    )
    if isinstance(raw, bool):
        raise YoutrackFillError(message)
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        raise YoutrackFillError(message) from None
    if not math.isfinite(hours) or hours <= 0 or hours > MAX_DAILY_HOURS:
        raise YoutrackFillError(message)
    return hours


def _workday_start(profile: UserProfile) -> time:
    raw = profile.youtrack.get("workday_start")
    if raw is None:
        return DEFAULT_WORKDAY_START
    if not isinstance(raw, str):
        raise ProfileConfigError("Workday start must use HH:MM format")
    match = WORKDAY_START_PATTERN.fullmatch(raw.strip())
    if match is None:
        raise ProfileConfigError("Workday start must use HH:MM format")
    hour, minute = int(match.group(1)), int(match.group(2))
    if hour > 23 or minute > 59:
        raise ProfileConfigError("Workday start must use HH:MM format")
    return time(hour, minute)


def _project_keys(
    profile: UserProfile, *issues: str | None
) -> tuple[str, ...]:
    keys: dict[str, None] = {}
    for issue in issues:
        if issue:
            keys.setdefault(issue.split("-", 1)[0], None)
    raw = profile.youtrack.get("project_keys")
    if raw is not None:
        if not isinstance(raw, list):
            raise ProfileConfigError(
                "Project keys must be a list of uppercase prefixes"
            )
        for item in raw:
            if not isinstance(item, str) or not PROJECT_KEY_PATTERN.fullmatch(
                item.strip()
            ):
                raise ProfileConfigError(
                    "Project keys must be a list of uppercase prefixes"
                )
            keys.setdefault(item.strip(), None)
    return tuple(keys)


def _default_comment(profile: UserProfile) -> str:
    raw = profile.youtrack.get("default_comment", DEFAULT_COMMENT)
    if not isinstance(raw, str) or not raw.strip():
        raise ProfileConfigError("Default comment must be a non-blank string")
    return raw.strip()


def _no_entries_message(warnings: list[str]) -> str:
    message = "Нечего планировать за запрошенный период"
    if warnings:
        message += ": " + warnings[0]
    return message