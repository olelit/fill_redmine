import asyncio
import json
from datetime import date
from pathlib import Path

from mcp.client import Client

from dto.worklog_dto import WorklogDTO
from mcp_server.app import create_server
from mcp_server.plans import PlanStore

SECRET_YOUTRACK = "youtrack-secret"
SECRET_REDMINE = "redmine-secret"


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def _user(**overrides: object) -> dict[str, object]:
    redmine: dict[str, object] = {
        "api_key": SECRET_REDMINE,
        "user_id": 16,
        "activity_id": 9,
        "comment": "development",
    }
    youtrack: dict[str, object] = {
        "access_token": SECRET_YOUTRACK,
        "issue_id": "DRIVEO-5062",
    }
    redmine.update(overrides.pop("redmine", {}))
    youtrack.update(overrides.pop("youtrack", {}))
    profile: dict[str, object] = {
        "name": "Oleg",
        "is_enable": True,
        "git_email": "oleg@example.com",
        "redmine": redmine,
        "youtrack": youtrack,
    }
    profile.update(overrides)
    return profile


def _install_fakes(monkeypatch, worklogs=(), redmine_entries=()):
    writes: list[object] = []
    deletes: list[object] = []

    class FakeTracker:
        def __init__(self, kind: str):
            self.kind = kind

        def get_worklogs(self, start, end):
            if self.kind == "youtrack":
                return list(worklogs)
            return []

        def get_time_entries(self, start, end):
            return list(redmine_entries)

        def create_worklogs(self, records):
            writes.append(list(records))
            return []

        def delete_time_entries(self, entry_ids):
            deletes.append(list(entry_ids))
            return []

    monkeypatch.setattr(
        "mcp_server.transfer_tools.build_user_tracker",
        lambda profile, kind, **kwargs: FakeTracker(kind),
    )
    return writes, deletes


def _call(
    path: Path,
    store: PlanStore,
    issue_id: int = 12345,
    start: str | None = "2026-10-20",
    end: str | None = "2026-10-21",
):
    arguments: dict[str, object] = {
        "user_name": "Oleg",
        "issue_id": issue_id,
    }
    if start is not None:
        arguments["start"] = start
    if end is not None:
        arguments["end"] = end

    async def call():
        async with Client(create_server(path, write_store=store)) as client:
            return await client.call_tool(
                "prepare_youtrack_transfer", arguments
            )

    return asyncio.run(call())


def _ok(result) -> dict[str, object]:
    assert result.is_error is False, str(result.content)
    return json.loads(result.content[0].text)


def _error(result) -> str:
    assert result.is_error is True, str(result.content)
    return str(result.content)


def test_prepare_aggregates_worklogs_and_plans_replacement(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    worklogs = [
        WorklogDTO(date="2026-10-20", hours=7.0, issue="DRIVEO-5062"),
        WorklogDTO(date="2026-10-20", hours=1.0, issue="DRIVEO-2542"),
        WorklogDTO(date="2026-10-21", hours=4.0, issue="DRIVEO-5183"),
    ]
    redmine_entries = [
        {
            "id": 901,
            "spent_on": "2026-10-20",
            "hours": 8.0,
            "issue": {"id": 111},
        },
        {
            "id": 902,
            "spent_on": "2026-10-22",
            "hours": 2.0,
            "issue": {"id": 222},
        },
    ]
    writes, deletes = _install_fakes(
        monkeypatch, worklogs, redmine_entries
    )
    store = PlanStore()

    data = _ok(_call(path, store))

    assert data["status"] == "plan_created"
    assert data["user"] == "Oleg"
    assert data["destination"] == {"tracker": "redmine", "issue": 12345}
    assert data["period"] == {
        "start": "2026-10-20",
        "end": "2026-10-21",
    }
    assert data["entries"] == [
        {
            "date": "2026-10-20",
            "issue": 12345,
            "hours": 8.0,
            "comment": "development",
            "source_issues": ["DRIVEO-2542", "DRIVEO-5062"],
            "replaces": [{"id": 901, "hours": 8.0}],
        },
        {
            "date": "2026-10-21",
            "issue": 12345,
            "hours": 4.0,
            "comment": "development",
            "source_issues": ["DRIVEO-5183"],
            "replaces": [],
        },
    ]
    assert data["warnings"] == []
    assert SECRET_YOUTRACK not in json.dumps(data)
    assert SECRET_REDMINE not in json.dumps(data)
    assert writes == []
    assert deletes == []

    plan = store.claim(data["plan_id"])
    assert plan.destination_kind == "redmine"
    assert plan.issue_id == "12345"
    assert [
        (deletion.date, deletion.entry_id, deletion.hours)
        for deletion in plan.deletions
    ] == [("2026-10-20", 901, 8.0)]


def test_prepare_uses_current_month_when_period_is_omitted(
    tmp_path, monkeypatch
):
    today = date.today()
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            WorklogDTO(
                date=today.isoformat(),
                hours=2.0,
                issue="DRIVEO-1",
            )
        ],
    )
    store = PlanStore()

    data = _ok(_call(path, store, start=None, end=None))

    assert data["period"] == {
        "start": f"{today.year:04d}-{today.month:02d}-01",
        "end": today.isoformat(),
    }


def test_prepare_warns_when_daily_hours_exceed_eight(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            WorklogDTO(date="2026-10-20", hours=7.0, issue="DRIVEO-1"),
            WorklogDTO(date="2026-10-20", hours=3.0, issue="DRIVEO-2"),
        ],
    )
    store = PlanStore()

    data = _ok(_call(path, store))

    assert data["entries"][0]["hours"] == 10.0
    assert data["warnings"] == [
        "2026-10-20: YouTrack hours 10 exceed 8"
    ]


def test_prepare_rejects_no_source_worklogs(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [])

    error = _error(_call(path, PlanStore()))

    assert "no youtrack worklogs" in error.lower()
    assert SECRET_YOUTRACK not in error


def test_prepare_rejects_missing_redmine_comment(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(redmine={"comment": "   "})])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(_call(path, PlanStore()))

    assert "redmine comment is required" in error.lower()
    assert SECRET_REDMINE not in error


def test_prepare_rejects_invalid_issue_id(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(_call(path, PlanStore(), issue_id=0))

    assert "positive integer" in error.lower()


def test_prepare_rejects_invalid_period(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(
        _call(
            path,
            PlanStore(),
            start="2026-10-21",
            end="2026-10-20",
        )
    )

    assert "start date must not be after end date" in error.lower()


def test_prepare_rejects_redmine_entry_without_id(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
        [{"spent_on": "2026-10-20", "hours": 8.0}],
    )

    error = _error(_call(path, PlanStore()))

    assert "redmine time entry id is missing" in error.lower()