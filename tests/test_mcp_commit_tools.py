import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from mcp import types
from mcp.client import Client

from dto.git_commit_dto import GitCommitDTO
from dto.worklog_dto import WorklogDTO
from mcp_server.app import create_server
from mcp_server.plans import PlanStore

SECRET = "youtrack-secret"
DAILY_ISSUE = "DRIVEO-2542"
DAY = "2026-10-20"  # Tuesday
NEXT_DAY = "2026-10-21"  # Wednesday


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def _user(**youtrack: object) -> dict[str, object]:
    config: dict[str, object] = {"access_token": SECRET}
    config.update(youtrack)
    return {
        "name": "Oleg",
        "is_enable": True,
        "git_email": "oleg@example.com",
        "youtrack": config,
    }


def _commit(
    commit_hash: str,
    day: str,
    subject: str = "",
    at: str = "10:00",
    body: str = "",
) -> GitCommitDTO:
    return GitCommitDTO(
        hash=commit_hash,
        author_name="Oleg",
        author_email="oleg@example.com",
        date=f"{day}T{at}:00+03:00",
        subject=subject,
        body=body,
    )


def _install_fakes(monkeypatch, commits, worklogs=()):
    writes: list[object] = []

    class FakeGitClient:
        def __init__(self, repo_path: str):
            self.repo_path = repo_path

        def list_commits(self, email, start, end):
            return list(commits)

    class FakeTracker:
        def get_worklogs(self, start, end):
            return list(worklogs)

        def create_worklogs(self, records):
            writes.append(records)
            return []

    monkeypatch.setattr("mcp_server.commit_tools.GitClient", FakeGitClient)
    monkeypatch.setattr(
        "mcp_server.commit_tools.build_user_tracker",
        lambda profile, kind, **kwargs: FakeTracker(),
    )
    return writes


def _call(
    path: Path,
    store: PlanStore,
    *,
    start: str | None = None,
    end: str | None = None,
    daily_hours: float | None = None,
):
    arguments: dict[str, object] = {
        "user_name": "Oleg",
        "repo_path": "/repo",
    }
    if start is not None:
        arguments["start"] = start
    if end is not None:
        arguments["end"] = end
    if daily_hours is not None:
        arguments["daily_hours"] = daily_hours

    async def call():
        async with Client(create_server(path, write_store=store)) as client:
            return await client.call_tool(
                "prepare_youtrack_from_commits", arguments
            )

    return asyncio.run(call())


def _ok(result) -> dict[str, object]:
    assert result.is_error is False, str(result.content)
    return json.loads(result.content[0].text)


def _error(result) -> str:
    assert result.is_error is True, str(result.content)
    return str(result.content)


def _hours_by_date(data: dict[str, object]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for entry in data["entries"]:
        totals[entry["date"]] = totals.get(entry["date"], 0.0) + entry["hours"]
    return totals


def test_prepare_today_defaults_to_today_and_eight_hours(tmp_path, monkeypatch):
    today = date.today().isoformat()
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [_commit("h1", today, "DRIVEO-1 implement")])
    store = PlanStore()

    data = _ok(_call(path, store))

    assert data["status"] == "plan_created"
    assert data["user"] == "Oleg"
    assert data["period"] == {"start": today, "end": today}
    assert data["daily_hours"] == 8.0
    assert data["warnings"] == []
    assert data["entries"] == [
        {
            "date": today,
            "issue": "DRIVEO-1",
            "hours": 8.0,
            "comment": "DRIVEO-1 implement",
            "commit_hashes": ["h1"],
        }
    ]
    assert SECRET not in json.dumps(data)

    plan = store.claim(data["plan_id"])
    assert plan.destination_kind == "youtrack"
    assert plan.issue_id == ""
    assert [(entry.date, entry.issue_id, entry.hours) for entry in plan.entries] == [
        (today, "DRIVEO-1", 8.0)
    ]


def test_prepare_respects_existing_hours_and_daily_meeting(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            _user(
                daily_meeting_issue_id=DAILY_ISSUE,
                daily_meeting_hours=1.0,
            )
        ],
    )
    _install_fakes(
        monkeypatch,
        [_commit("h1", DAY, "DRIVEO-1 implement")],
        [WorklogDTO(date=DAY, hours=2.0, issue="DRIVEO-9")],
    )
    store = PlanStore()

    data = _ok(_call(path, store, start=DAY, end=DAY))

    assert data["entries"] == [
        {
            "date": DAY,
            "issue": DAILY_ISSUE,
            "hours": 1.0,
            "comment": "Daily meeting",
            "commit_hashes": [],
        },
        {
            "date": DAY,
            "issue": "DRIVEO-1",
            "hours": 5.0,
            "comment": "DRIVEO-1 implement",
            "commit_hashes": ["h1"],
        },
    ]
    assert data["warnings"] == []
    assert sum(entry["hours"] for entry in data["entries"]) + 2.0 == 8.0
    assert SECRET not in json.dumps(data)


def test_prepare_uses_fallback_when_no_commits(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(issue_id="DRIVEO-5062")])
    _install_fakes(monkeypatch, [])
    store = PlanStore()

    data = _ok(_call(path, store, start=DAY, end=DAY))

    assert data["entries"] == [
        {
            "date": DAY,
            "issue": "DRIVEO-5062",
            "hours": 8.0,
            "comment": "development",
            "commit_hashes": [],
        }
    ]
    assert any("no commits" in warning for warning in data["warnings"])
    assert SECRET not in json.dumps(data)


def test_prepare_explicit_period_tracks_each_day(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(issue_id="DRIVEO-5062")])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", "2026-10-18", "DRIVEO-3 outside period"),
            _commit("h2", "2026-10-19", "DRIVEO-1 start"),
            _commit("h3", NEXT_DAY, "DRIVEO-2 review"),
        ],
    )
    store = PlanStore()

    data = _ok(_call(path, store, start="2026-10-19", end=NEXT_DAY))

    assert data["period"] == {"start": "2026-10-19", "end": NEXT_DAY}
    assert data["daily_hours"] == 8.0
    assert _hours_by_date(data) == {
        "2026-10-19": 8.0,
        DAY: 8.0,
        NEXT_DAY: 8.0,
    }
    issues = {entry["date"]: entry["issue"] for entry in data["entries"]}
    assert issues == {
        "2026-10-19": "DRIVEO-1",
        DAY: "DRIVEO-5062",
        NEXT_DAY: "DRIVEO-2",
    }
    assert "DRIVEO-3" not in json.dumps(data)


def test_prepare_does_not_write(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    writes = _install_fakes(
        monkeypatch,
        [_commit("h1", DAY, "DRIVEO-1 implement")],
    )
    store = PlanStore()

    data = _ok(_call(path, store, start=DAY, end=DAY))

    assert data["status"] == "plan_created"
    assert store.claim(data["plan_id"]).destination_kind == "youtrack"
    assert writes == []


def test_prepare_then_write_plan_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [_commit("h1", DAY, "DRIVEO-1 implement")])
    written: list[WorklogDTO] = []

    class WritingTracker:
        def create_worklogs(self, records):
            written.extend(records)
            return []

    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda profile, kind, **kwargs: WritingTracker(),
    )
    store = PlanStore()
    server = create_server(path, write_store=store)

    async def elicitation_callback(context, params):
        return types.ElicitResult(action="accept", content={"approved": True})

    async def round_trip():
        async with Client(
            server, mode="legacy", elicitation_callback=elicitation_callback
        ) as client:
            prepared = await client.call_tool(
                "prepare_youtrack_from_commits",
                {
                    "user_name": "Oleg",
                    "repo_path": "/repo",
                    "start": DAY,
                    "end": DAY,
                },
            )
            data = _ok(prepared)
            result = await client.call_tool(
                "write_plan", {"plan_id": data["plan_id"]}
            )
            return data, result

    data, result = asyncio.run(round_trip())

    assert result.is_error is False, str(result.content)
    assert len(written) == 1
    record = written[0]
    planned = data["entries"][0]
    assert record.date == planned["date"]
    assert record.issue == planned["issue"]
    assert record.hours == planned["hours"]
    assert record.description == planned["comment"]
    assert record.source == "youtrack"


def test_prepare_skips_daily_meeting_already_recorded(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            _user(
                daily_meeting_issue_id=DAILY_ISSUE,
                daily_meeting_hours=1.0,
            )
        ],
    )
    _install_fakes(
        monkeypatch,
        [_commit("h1", DAY, "DRIVEO-1 implement")],
        [WorklogDTO(date=DAY, hours=1.0, issue=DAILY_ISSUE)],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY))

    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["issue"] == "DRIVEO-1"
    assert entry["hours"] == 7.0
    assert entry["comment"] == "DRIVEO-1 implement"
    assert data["warnings"] == []


def test_prepare_honors_smaller_daily_hours(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [_commit("h1", DAY, "DRIVEO-1 implement")])

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY, daily_hours=4))

    assert data["daily_hours"] == 4.0
    assert _hours_by_date(data) == {DAY: 4.0}


def test_prepare_quantizes_fractional_remainder(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(issue_id="DRIVEO-5062")])
    _install_fakes(
        monkeypatch,
        [],
        [WorklogDTO(date=DAY, hours=2.3, issue="DRIVEO-9")],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY))

    assert _hours_by_date(data) == {DAY: 5.5}
    assert any(
        "half-hour units" in warning for warning in data["warnings"]
    )


def test_prepare_one_sided_period(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    today = date.today()
    past = (today - timedelta(days=2)).isoformat()
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch, [_commit("h1", past, "DRIVEO-1 implement")]
    )

    data = _ok(_call(path, PlanStore(), start=past))

    assert data["period"] == {"start": past, "end": today.isoformat()}

    _install_fakes(
        monkeypatch, [_commit("h1", past, "DRIVEO-1 implement")]
    )
    error = _error(_call(path, PlanStore(), end=past))

    assert "Start date must not be after end date" in error


@pytest.mark.parametrize("daily_hours", [0, -1, 9, float("nan")])
def test_prepare_rejects_invalid_daily_hours(
    tmp_path, monkeypatch, daily_hours
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    writes = _install_fakes(
        monkeypatch, [_commit("h1", DAY, "DRIVEO-1 implement")]
    )

    error = _error(_call(path, PlanStore(), start=DAY, end=DAY, daily_hours=daily_hours))

    assert "daily_hours" in error
    assert SECRET not in error
    assert writes == []


def test_prepare_skips_full_day(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", DAY, "DRIVEO-1 implement"),
            _commit("h2", NEXT_DAY, "DRIVEO-2 review"),
        ],
        [WorklogDTO(date=DAY, hours=8.0, issue="DRIVEO-9")],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=NEXT_DAY))

    assert _hours_by_date(data) == {NEXT_DAY: 8.0}
    assert any("already" in warning for warning in data["warnings"])


def test_prepare_rejects_no_commits_without_fallback(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    writes = _install_fakes(monkeypatch, [])

    error = _error(_call(path, PlanStore(), start=DAY, end=DAY))

    assert "no commits" in error.lower()
    assert "fallback" in error.lower()
    assert SECRET not in error
    assert writes == []


def test_prepare_merges_issue_seen_in_multiple_commits(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", DAY, "DRIVEO-1 start", at="10:00"),
            _commit("h2", DAY, "DRIVEO-1 continue", at="13:00"),
            _commit("h3", DAY, "DRIVEO-1 wrap up", at="17:00"),
        ],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY))

    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["issue"] == "DRIVEO-1"
    assert entry["hours"] == 8.0
    assert entry["commit_hashes"] == ["h1", "h2", "h3"]


def test_prepare_merges_daily_meeting_and_commit_for_the_same_issue(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            _user(
                daily_meeting_issue_id="DRIVEO-1",
                daily_meeting_hours=1.0,
            )
        ],
    )
    _install_fakes(
        monkeypatch,
        [_commit("h1", DAY, "DRIVEO-1 implement")],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY))

    assert len(data["entries"]) == 1
    entry = data["entries"][0]
    assert entry["issue"] == "DRIVEO-1"
    assert entry["hours"] == 8.0
    assert entry["commit_hashes"] == ["h1"]
    assert "Daily meeting" in entry["comment"]
    assert "implement" in entry["comment"]


def test_prepare_honors_configured_workday_start(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(workday_start="11:00")])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", DAY, "DRIVEO-1 quick", at="10:00"),
            _commit("h2", DAY, "DRIVEO-2 long", at="12:00"),
        ],
    )

    data = _ok(_call(path, PlanStore(), start=DAY, end=DAY))

    assert {
        entry["issue"]: entry["hours"] for entry in data["entries"]
    } == {"DRIVEO-2": 7.5, "DRIVEO-1": 0.5}


@pytest.mark.parametrize("workday_start", ["9am", "25:00", 9])
def test_prepare_rejects_invalid_workday_start(
    tmp_path, monkeypatch, workday_start
):
    path = tmp_path / "users.json"
    _write_users(path, [_user(workday_start=workday_start)])
    writes = _install_fakes(
        monkeypatch, [_commit("h1", DAY, "DRIVEO-1 implement")]
    )

    error = _error(_call(path, PlanStore(), start=DAY, end=DAY))

    assert "HH:MM" in error
    assert SECRET not in error
    assert writes == []


def test_prepare_rejects_blank_default_comment(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(default_comment="   ")])
    writes = _install_fakes(
        monkeypatch, [_commit("h1", DAY, "DRIVEO-1 implement")]
    )

    error = _error(_call(path, PlanStore(), start=DAY, end=DAY))

    assert "comment" in error.lower()
    assert SECRET not in error
    assert writes == []


def test_server_lists_new_tool(tmp_path):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    server = create_server(path)

    async def inspect_server():
        async with Client(server) as client:
            return await client.list_tools()

    tools = asyncio.run(inspect_server()).tools
    names = [tool.name for tool in tools]
    assert "prepare_youtrack_from_commits" in names

    tool = next(
        tool for tool in tools if tool.name == "prepare_youtrack_from_commits"
    )
    description = tool.description or ""
    assert "коммит" in description.lower()
    assert "write_plan" in description