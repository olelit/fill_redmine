import asyncio
import json
import os
import subprocess
from pathlib import Path

import pytest
from mcp.client import Client

from mcp_server.app import create_server
from mcp_server.config import ProfileConfigError, UserProfile, load_users
from mcp_server.read_tools import get_git_commits, get_worklogs
from mcp_server.tracker_access import build_user_tracker, required_redmine_comment


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def _call_tool(server, name: str, arguments: dict[str, object]):
    async def call():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(call())


def _tool_data(result):
    assert result.is_error is False
    return [json.loads(item.text) for item in result.content]


def test_redmine_read_needs_no_saved_issue_and_returns_no_credentials(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            {
                "name": "Oleg",
                "is_enable": True,
                "redmine": {"api_key": "redmine-secret", "user_id": 17, "activity_id": 9},
            }
        ],
    )
    monkeypatch.setattr(
        "clients.redmine_client.RedmineClient.get_time_entries",
        lambda self, user_id, start, end: [
            {
                "spent_on": "2026-10-20",
                "hours": 1.5,
                "comments": "Review",
                "issue": {"id": 42},
            }
        ],
    )

    tracker = build_user_tracker(load_users(path)[0], "redmine")
    assert "issue_id" not in tracker.config
    result = _tool_data(
        _call_tool(
            create_server(path),
            "get_worklogs",
            {"user_name": "Oleg", "tracker": "redmine", "start": "2026-10-20", "end": "2026-10-20"},
        )
    )

    assert result == [
        {
            "date": "2026-10-20",
            "hours": 1.5,
            "description": "Review",
            "issue": "42",
            "source": "redmine",
        }
    ]
    assert "redmine-secret" not in json.dumps(result)
    monkeypatch.setattr("mcp_server.read_tools.default_users_path", lambda: path)
    assert get_worklogs("Oleg", "redmine", "2026-10-20", "2026-10-20") == result


def test_youtrack_read_uses_profile_token_and_aggregates_daily_worklogs(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            {
                "name": "Oleg",
                "is_enable": True,
                "youtrack": {"access_token": "youtrack-secret", "issue_id": "APP-1"},
            }
        ],
    )
    monkeypatch.setattr(
        "clients.youtrack_client.YoutrackClient.get_work_items",
        lambda self, start_date, end_date: [
            {"date": 1792497600000, "duration": {"minutes": 30}},
            {"date": 1792512000000, "duration": {"minutes": 90}},
        ],
    )

    result = _tool_data(
        _call_tool(
            create_server(path),
            "get_worklogs",
            {"user_name": "Oleg", "tracker": "youtrack", "start": "2026-10-20", "end": "2026-10-20"},
        )
    )

    assert result == [{"date": "2026-10-20", "hours": 2.0, "description": "", "issue": "", "source": "youtrack"}]
    assert "youtrack-secret" not in json.dumps(result)


@pytest.mark.parametrize(
    ("start", "end"),
    [("20-10-2026", "2026-10-21"), ("2026-10-22", "2026-10-21")],
)
def test_worklog_date_range_validation_returns_safe_tool_error(tmp_path, start, end):
    path = tmp_path / "users.json"
    _write_users(path, [{"name": "Oleg", "is_enable": True, "redmine": {}}])

    result = _call_tool(
        create_server(path),
        "get_worklogs",
        {"user_name": "Oleg", "tracker": "redmine", "start": start, "end": end},
    )

    assert result.is_error is True
    assert "date" in str(result.content).lower()


def test_read_tools_reject_disabled_profiles(tmp_path):
    path = tmp_path / "users.json"
    _write_users(path, [{"name": "Oleg", "is_enable": False, "redmine": {}}])

    result = _call_tool(
        create_server(path),
        "get_worklogs",
        {"user_name": "Oleg", "tracker": "redmine", "start": "2026-10-20", "end": "2026-10-20"},
    )

    assert result.is_error is True
    assert "enabled" in str(result.content).lower()


@pytest.mark.parametrize("field", ["user_id", "activity_id"])
@pytest.mark.parametrize("value", [17.9, True])
def test_redmine_adapter_rejects_non_integer_ids_without_exposing_values(field, value):
    profile = UserProfile(
        name="Oleg",
        is_enable=True,
        redmine={"api_key": "secret", "user_id": 17, "activity_id": 9, field: value},
    )

    with pytest.raises(ProfileConfigError) as exc_info:
        build_user_tracker(profile, "redmine")

    assert str(value) not in str(exc_info.value)


@pytest.mark.parametrize("value", [17, "17"])
def test_redmine_adapter_accepts_positive_integer_ids(value):
    profile = UserProfile(
        name="Oleg",
        is_enable=True,
        redmine={"api_key": "secret", "user_id": value, "activity_id": value},
    )

    tracker = build_user_tracker(profile, "redmine")

    assert tracker.config["user_id"] == value
    assert tracker.config["activity_id"] == value


def test_git_tool_returns_generic_error_for_invalid_repository_path(tmp_path):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "git_email": "oleg@example.com"}],
    )
    invalid_repo_path = str(tmp_path / "missing-repo")

    result = _call_tool(
        create_server(path),
        "get_git_commits",
        {
            "user_name": "Oleg",
            "repo_path": invalid_repo_path,
            "start": "2026-10-20",
            "end": "2026-10-20",
        },
    )

    assert result.is_error is True
    error = str(result.content)
    assert "Git commit read failed" in error
    assert invalid_repo_path not in error
    assert "oleg@example.com" not in error


def test_git_tool_returns_commit_metadata_without_profile_credentials(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "git_email": "oleg@example.com"}],
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Oleg"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "oleg@example.com"], check=True
    )
    (repo / "note.txt").write_text("commit body\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "note.txt"], check=True)
    env = os.environ.copy() | {
        "GIT_AUTHOR_DATE": "2026-10-20T10:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-10-20T10:00:00+00:00",
    }
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "Implement report", "-m", "commit body"],
        check=True,
        capture_output=True,
        env=env,
    )

    result = _tool_data(
        _call_tool(
            create_server(path),
            "get_git_commits",
            {"user_name": "Oleg", "repo_path": str(repo), "start": "2026-10-20", "end": "2026-10-20"},
        )
    )

    assert len(result) == 1
    assert result[0]["author_date"].startswith("2026-10-20T10:00:00")
    assert result[0]["subject"] == "Implement report"
    assert result[0]["body"] == "commit body"
    assert "oleg@example.com" not in json.dumps(result)
    monkeypatch.setattr("mcp_server.read_tools.default_users_path", lambda: path)
    assert get_git_commits("Oleg", str(repo), "2026-10-20", "2026-10-20") == result


def test_tracker_adapter_clones_config_and_requires_runtime_issue_for_write():
    profile = UserProfile(
        name="Oleg",
        is_enable=True,
        redmine={
            "api_key": "secret",
            "user_id": 3,
            "activity_id": 4,
            "comment": "  Work  ",
        },
    )

    tracker = build_user_tracker(profile, "redmine", issue_id=99, for_write=True)

    assert tracker.config["issue_id"] == 99
    assert "issue_id" not in profile.redmine
    assert required_redmine_comment(profile) == "Work"
    with pytest.raises(ProfileConfigError):
        build_user_tracker(profile, "redmine", for_write=True)


@pytest.mark.parametrize(
    ("kind", "config"),
    [
        ("redmine", {"api_key": " ", "user_id": 3, "activity_id": 4}),
        ("youtrack", {"access_token": " ", "issue_id": "APP-1"}),
        ("youtrack", {"access_token": "hidden-token", "issue_id": " "}),
    ],
)
def test_tracker_adapter_rejects_blank_required_fields_without_exposing_credentials(
    kind, config
):
    profile = UserProfile(name="Oleg", is_enable=True, **{kind: config})

    with pytest.raises(ProfileConfigError) as exc_info:
        build_user_tracker(profile, kind)

    assert "hidden-token" not in str(exc_info.value)


def test_server_registers_read_tools_and_write_gate(tmp_path):
    path = tmp_path / "users.json"
    _write_users(path, [{"name": "Oleg", "is_enable": True}])

    async def inspect():
        async with Client(create_server(path)) as client:
            return await client.list_tools()

    tools = asyncio.run(inspect())

    assert [tool.name for tool in tools.tools] == [
        "list_enabled_users",
        "get_worklogs",
        "get_git_commits",
        "write_plan",
    ]
    assert "users_path" not in str(tools.tools)
