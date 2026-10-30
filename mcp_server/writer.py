from pathlib import Path

from dto.worklog_dto import WorklogDTO
from mcp_server.config import ProfileConfigError, UserProfile, load_users, select_user
from mcp_server.plans import PlannedEntry, WritePlan, fingerprint_target_config, plan_entry_issue
from mcp_server.tracker_access import build_user_tracker


def execute_plan(plan: WritePlan, users_path: Path) -> dict[str, object]:
    if plan.destination_kind not in ("redmine", "youtrack"):
        raise ProfileConfigError("Unsupported tracker kind")

    profile = select_user(load_users(users_path), plan.user_name)
    if fingerprint_target_config(profile, plan.destination_kind) != plan.target_fingerprint:
        raise ProfileConfigError("Destination tracker configuration changed since plan creation")
    if plan.destination_kind == "redmine":
        return _execute_redmine(plan, profile)
    return _execute_youtrack(plan, profile)


def _execute_redmine(plan: WritePlan, profile: UserProfile) -> dict[str, object]:
    tracker = build_user_tracker(
        profile,
        "redmine",
        issue_id=_redmine_issue_id(plan.issue_id),
        for_write=True,
    )
    failed_reasons: dict[str, str] = {}
    if plan.deletions:
        deletion_errors = tracker.delete_time_entries(
            [deletion.entry_id for deletion in plan.deletions]
        )
        failed_ids = {
            entry_id for entry_id, _message in deletion_errors
        }
        for deletion in plan.deletions:
            if deletion.entry_id in failed_ids:
                failed_reasons.setdefault(deletion.date, "delete_failed")

    records = [
        _record(plan, entry, plan.issue_id)
        for entry in plan.entries
        if entry.date not in failed_reasons
    ]
    if records:
        failures = tracker.create_worklogs(records)
        for entry_date, _message in failures:
            failed_reasons.setdefault(entry_date, "create_failed")

    results: list[dict[str, object]] = []
    for entry in plan.entries:
        reason = failed_reasons.get(entry.date)
        result: dict[str, object] = {
            "date": entry.date,
            "issue": plan.issue_id,
            "status": "failed" if reason else "created",
        }
        if reason:
            result["reason"] = reason
        results.append(result)

    return {"results": results}


def _execute_youtrack(plan: WritePlan, profile: UserProfile) -> dict[str, object]:
    groups: dict[str, list[tuple[int, PlannedEntry]]] = {}
    for index, entry in enumerate(plan.entries):
        issue = plan_entry_issue(plan, entry)
        if not issue:
            raise ProfileConfigError("YouTrack write requires a valid issue ID")
        groups.setdefault(issue, []).append((index, entry))

    failed: set[int] = set()
    for issue, indexed_entries in groups.items():
        try:
            tracker = build_user_tracker(
                profile,
                "youtrack",
                issue_id=issue,
                for_write=True,
            )
            group_failures = tracker.create_worklogs(
                [_record(plan, entry, issue) for _index, entry in indexed_entries]
            )
        except Exception:
            failed.update(index for index, _entry in indexed_entries)
            continue
        failed_dates = {entry_date for entry_date, _message in group_failures}
        failed.update(
            index for index, entry in indexed_entries if entry.date in failed_dates
        )

    return {
        "results": [
            {
                "date": entry.date,
                "issue": plan_entry_issue(plan, entry),
                "status": "failed" if index in failed else "created",
            }
            for index, entry in enumerate(plan.entries)
        ]
    }


def _record(plan: WritePlan, entry: PlannedEntry, issue: str) -> WorklogDTO:
    return WorklogDTO(
        date=entry.date,
        hours=entry.hours,
        description=entry.comment,
        issue=issue,
        source=plan.destination_kind,
    )


def _redmine_issue_id(raw_issue_id: str) -> int:
    try:
        issue_id = int(raw_issue_id)
    except (TypeError, ValueError):
        raise ProfileConfigError("Redmine write requires a valid issue ID") from None
    if issue_id <= 0:
        raise ProfileConfigError("Redmine write requires a valid issue ID")
    return issue_id
