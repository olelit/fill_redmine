import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from mcp.client import Client

from dto.git_commit_dto import GitCommitDTO
from dto.worklog_dto import WorklogDTO
from mcp_server.app import create_server
from mcp_server.plans import PlanStore
from mcp_server.youtrack_tools import _default_period

SECRET = "youtrack-secret"
DAILY_ISSUE = "DRIVEO-2542"


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
    commit_hash: str, day: str, subject: str = "", body: str = ""
) -> GitCommitDTO:
    return GitCommitDTO(
        hash=commit_hash,
        author_name="Oleg",
        author_email="oleg@example.com",
        date=f"{day}T10:00:00+00:00",
        subject=subject,
        body=body,
    )


def _entry(
    day: str = "2026-10-20",
    issue: str = "DRIVEO-1",
    hours: float = 2.0,
    comment: str = "Implement",
    hashes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "date": day,
        "issue_id": issue,
        "hours": hours,
        "comment": comment,
        "commit_hashes": [] if hashes is None else hashes,
    }


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

    monkeypatch.setattr(
        "mcp_server.youtrack_tools.GitClient", FakeGitClient
    )
    monkeypatch.setattr(
        "mcp_server.youtrack_tools.build_user_tracker",
        lambda profile, kind, **kwargs: FakeTracker(),
    )
    return writes


def _call(path: Path, store: PlanStore, entries, start="2026-10-19", end="2026-10-25"):
    arguments: dict[str, object] = {
        "user_name": "Oleg",
        "repo_path": "/repo",
        "entries": entries,
    }
    if start is not None:
        arguments["start"] = start
    if end is not None:
        arguments["end"] = end

    async def call():
        async with Client(create_server(path, write_store=store)) as client:
            return await client.call_tool("prepare_youtrack_fill", arguments)

    return asyncio.run(call())


def _ok(result) -> dict[str, object]:
    assert result.is_error is False, str(result.content)
    return json.loads(result.content[0].text)


def _error(result) -> str:
    assert result.is_error is True, str(result.content)
    return str(result.content)


def test_prepare_creates_plan_for_two_issues_on_one_day_without_writing(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    commits = [
        _commit("h1", "2026-10-20", "DRIVEO-1 implement report"),
        _commit("h2", "2026-10-20", "DRIVEO-2 fix export"),
    ]
    worklogs = [WorklogDTO(date="2026-10-20", hours=1.0, issue="DRIVEO-9")]
    writes = _install_fakes(monkeypatch, commits, worklogs)
    store = PlanStore()

    result = _call(
        path,
        store,
        [
            _entry(hours=3.5, hashes=["h1"]),
            _entry(
                issue="DRIVEO-2",
                hours=3.5,
                comment="Fix export",
                hashes=["h2"],
            ),
        ],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["status"] == "plan_created"
    assert data["user"] == "Oleg"
    assert data["period"] == {"start": "2026-10-20", "end": "2026-10-20"}
    assert data["warnings"] == []
    assert data["entries"] == [
        {
            "date": "2026-10-20",
            "issue": "DRIVEO-1",
            "hours": 3.5,
            "comment": "Implement",
            "commit_hashes": ["h1"],
        },
        {
            "date": "2026-10-20",
            "issue": "DRIVEO-2",
            "hours": 3.5,
            "comment": "Fix export",
            "commit_hashes": ["h2"],
        },
    ]
    assert SECRET not in json.dumps(data)
    assert writes == []

    plan = store.claim(data["plan_id"])
    assert plan.destination_kind == "youtrack"
    assert plan.issue_id == ""
    assert [
        (entry.date, entry.issue_id, entry.hours, entry.commit_hashes)
        for entry in plan.entries
    ] == [
        ("2026-10-20", "DRIVEO-1", 3.5, ("h1",)),
        ("2026-10-20", "DRIVEO-2", 3.5, ("h2",)),
    ]


def test_prepare_warns_when_issue_is_absent_from_commit_subjects(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "Unrelated refactoring")],
    )
    store = PlanStore()

    result = _call(
        path,
        store,
        [_entry(issue="DRIVEO-2", hours=2.0, hashes=["h1"])],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["warnings"] == [
        "2026-10-20: issue DRIVEO-2 not found in commit subjects"
    ]
    assert data["entries"][0]["issue"] == "DRIVEO-2"


def test_prepare_normalizes_issue_and_finds_it_in_commit_body(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "Refactor", body="References driveo-7")],
    )
    store = PlanStore()

    result = _call(
        path,
        store,
        [_entry(issue="  driveo-7  ", hours=2.0, hashes=["h1"])],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["warnings"] == []
    assert data["entries"][0]["issue"] == "DRIVEO-7"


def test_prepare_accepts_daily_meeting_without_commit_hashes(tmp_path, monkeypatch):
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
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )
    store = PlanStore()

    result = _call(
        path,
        store,
        [
            _entry(
                issue=DAILY_ISSUE,
                hours=1.0,
                comment="Daily meeting",
                hashes=[],
            ),
            _entry(issue="DRIVEO-1", hours=2.0, hashes=["h1"]),
        ],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["warnings"] == []
    assert [entry["issue"] for entry in data["entries"]] == [DAILY_ISSUE, "DRIVEO-1"]
    plan = store.claim(data["plan_id"])
    assert [entry.issue_id for entry in plan.entries] == [DAILY_ISSUE, "DRIVEO-1"]


def test_prepare_accepts_daily_meeting_with_default_hours(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(daily_meeting_issue_id=DAILY_ISSUE)])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )
    store = PlanStore()

    result = _call(
        path,
        store,
        [
            _entry(
                issue=DAILY_ISSUE,
                hours=1.0,
                comment="Daily meeting",
                hashes=[],
            )
        ],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["entries"][0]["hours"] == 1.0
    assert data["warnings"] == []


def test_prepare_rejects_fractional_daily_meeting_hours(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            _user(
                daily_meeting_issue_id=DAILY_ISSUE,
                daily_meeting_hours=0.7,
            )
        ],
    )
    writes = _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )

    error = _error(
        _call(
            path,
            PlanStore(),
            [
                _entry(
                    issue=DAILY_ISSUE,
                    hours=1.0,
                    comment="Daily meeting",
                    hashes=[],
                )
            ],
            start="2026-10-20",
            end="2026-10-20",
        )
    )

    assert "multiple of 0.5" in error
    assert SECRET not in error
    assert writes == []


def test_prepare_accepts_fallback_issue_without_commits(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(issue_id="DRIVEO-5062")])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )
    store = PlanStore()

    result = _call(
        path,
        store,
        [
            _entry(
                issue="DRIVEO-5062",
                hours=7.0,
                comment="development",
                hashes=[],
            )
        ],
        start="2026-10-20",
        end="2026-10-20",
    )
    data = _ok(result)

    assert data["warnings"] == [
        "2026-10-20: no commits; filled on fallback issue DRIVEO-5062"
    ]
    plan = store.claim(data["plan_id"])
    assert plan.entries[0].issue_id == "DRIVEO-5062"
    assert plan.entries[0].commit_hashes == ()


def test_prepare_rejects_no_commits_for_non_fallback_issue(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user(issue_id="DRIVEO-5062")])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )

    result = _call(
        path,
        PlanStore(),
        [_entry(issue="DRIVEO-1", hours=7.0, hashes=[])],
        start="2026-10-20",
        end="2026-10-20",
    )

    assert "commit hashes are required" in _error(result).lower()


def test_prepare_uses_the_current_month_when_period_is_omitted(
    tmp_path, monkeypatch
):
    today = date.today()
    day = today.isoformat()
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [_commit("h1", day, "DRIVEO-1 implement")])
    store = PlanStore()

    result = _call(
        path,
        store,
        [_entry(day=day, hours=2.0, hashes=["h1"])],
        start=None,
        end=None,
    )
    data = _ok(result)

    assert data["period"] == {
        "start": f"{today.year:04d}-{today.month:02d}-01",
        "end": day,
    }


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        (
            [
                _entry(
                    issue=DAILY_ISSUE,
                    hours=0.5,
                    comment="Daily meeting",
                    hashes=[],
                )
            ],
            "daily meeting hours",
        ),
        (
            [
                _entry(
                    day="2026-10-24",
                    issue=DAILY_ISSUE,
                    hours=1.0,
                    comment="Daily meeting",
                    hashes=[],
                )
            ],
            "working day",
        ),
        (
            [_entry(issue="DRIVEO-1", hours=1.0, hashes=[])],
            "commit hashes",
        ),
    ],
)
def test_prepare_rejects_invalid_daily_meeting_rows(
    tmp_path, monkeypatch, entries, expected
):
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
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )

    result = _call(path, PlanStore(), entries)

    error = _error(result)
    assert expected in error.lower()
    assert SECRET not in error


def test_prepare_rejects_hashless_entry_without_daily_or_fallback_config(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
    )

    result = _call(
        path,
        PlanStore(),
        [_entry(issue="DRIVEO-1", hours=1.0, hashes=[])],
        start="2026-10-20",
        end="2026-10-20",
    )

    error = _error(result)
    assert "commit hashes are required" in error.lower()
    assert "commit hashes" in error.lower()


def test_prepare_rejects_daily_meeting_already_recorded(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [_user(daily_meeting_issue_id=DAILY_ISSUE)],
    )
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-20", "DRIVEO-1 implement")],
        [WorklogDTO(date="2026-10-20", hours=1.0, issue=DAILY_ISSUE)],
    )

    result = _call(
        path,
        PlanStore(),
        [
            _entry(
                issue=DAILY_ISSUE,
                hours=1.0,
                comment="Daily meeting",
                hashes=[],
            )
        ],
        start="2026-10-20",
        end="2026-10-20",
    )

    error = _error(result)
    assert "already" in error.lower()
    assert SECRET not in error


def test_prepare_rejects_empty_commit_list(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [])

    result = _call(
        path,
        PlanStore(),
        [_entry(hours=2.0, hashes=["h1"])],
        start="2026-10-20",
        end="2026-10-20",
    )

    assert "no commits" in _error(result).lower()


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([_entry(hours=2.0, hashes=["other"])], "unknown commit"),
        ([_entry(hours=1.25, hashes=["h1"])], "multiple of 0.5"),
        (
            [
                _entry(hours=4.0, comment="One", hashes=["h1"]),
                _entry(
                    issue="DRIVEO-2",
                    hours=4.5,
                    comment="Two",
                    hashes=["h2"],
                ),
            ],
            "8-hour",
        ),
        (
            [
                _entry(hours=2.0, hashes=["h1"]),
                _entry(hours=2.0, comment="Again", hashes=["h2"]),
            ],
            "duplicate",
        ),
        ([_entry(hours=2.0, comment="   ", hashes=["h1"])], "comment"),
        ([_entry(issue="DRIVEO", hours=2.0, hashes=["h1"])], "issue"),
        ([_entry(day="2026-10-26", hours=2.0, hashes=["h1"])], "period"),
        ([_entry(day="20-10-2026", hours=2.0, hashes=["h1"])], "YYYY-MM-DD"),
    ],
)
def test_prepare_rejects_invalid_entries(tmp_path, monkeypatch, entries, expected):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", "2026-10-20", "DRIVEO-1 implement"),
            _commit("h2", "2026-10-20", "DRIVEO-2 fix"),
        ],
        [WorklogDTO(date="2026-10-20", hours=1.0, issue="DRIVEO-9")],
    )

    result = _call(path, PlanStore(), entries)

    error = _error(result)
    assert expected.lower() in error.lower()
    assert SECRET not in error


def test_prepare_rejects_commit_from_another_date(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [_commit("h1", "2026-10-19", "DRIVEO-1 implement")],
    )

    result = _call(
        path,
        PlanStore(),
        [_entry(day="2026-10-20", hours=2.0, hashes=["h1"])],
        start="2026-10-19",
        end="2026-10-20",
    )

    error = _error(result)
    assert "belongs to 2026-10-19" in error


def test_prepare_rejects_existing_plus_proposed_above_eight_hours(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            _commit("h1", "2026-10-20", "DRIVEO-1 implement"),
            _commit("h2", "2026-10-20", "DRIVEO-2 fix"),
        ],
        [WorklogDTO(date="2026-10-20", hours=1.0, issue="DRIVEO-9")],
    )

    result = _call(
        path,
        PlanStore(),
        [
            _entry(hours=4.0, comment="One", hashes=["h1"]),
            _entry(
                issue="DRIVEO-2",
                hours=3.5,
                comment="Two",
                hashes=["h2"],
            ),
        ],
        start="2026-10-20",
        end="2026-10-20",
    )

    assert "8-hour" in _error(result).lower()


def test_default_period_starts_on_the_first_day_of_the_current_month():
    assert _default_period(date(2026, 10, 29)) == (
        date(2026, 10, 1),
        date(2026, 10, 29),
    )
    assert _default_period(date(2026, 1, 15)) == (
        date(2026, 1, 1),
        date(2026, 1, 15),
    )
