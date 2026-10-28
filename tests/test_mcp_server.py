import asyncio
import json
from pathlib import Path

from mcp.client import Client

from mcp_server.app import create_server
from mcp_server.user_tools import list_enabled_users


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def test_list_enabled_users_only_returns_names_and_configured_trackers(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            {
                "name": "Oleg",
                "is_enable": True,
                "git_email": "private@example.com",
                "redmine": {"api_key": "redmine-secret", "comment": "private comment"},
                "youtrack": {},
            },
            {"name": "No trackers", "is_enable": True},
        ],
    )
    monkeypatch.setattr("mcp_server.user_tools.default_users_path", lambda: path)

    result = list_enabled_users()

    assert result == [
        {"name": "Oleg", "trackers": "redmine"},
        {"name": "No trackers", "trackers": ""},
    ]


def test_list_enabled_users_excludes_disabled_profiles(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            {"name": "Enabled", "is_enable": True, "youtrack": {"access_token": "secret"}},
            {"name": "Disabled", "is_enable": False, "redmine": {"api_key": "secret"}},
        ],
    )
    monkeypatch.setattr("mcp_server.user_tools.default_users_path", lambda: path)

    assert list_enabled_users() == [{"name": "Enabled", "trackers": "youtrack"}]


def test_list_enabled_users_never_returns_profile_secrets(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [
            {
                "name": "Oleg",
                "is_enable": True,
                "git_email": "private@example.com",
                "redmine": {"api_key": "redmine-secret", "user_id": 123},
                "youtrack": {"access_token": "youtrack-secret", "issue_id": "PROJECT-1"},
            }
        ],
    )
    monkeypatch.setattr("mcp_server.user_tools.default_users_path", lambda: path)

    result = json.dumps(list_enabled_users())

    for private_value in ("redmine-secret", "youtrack-secret", "private@example.com", "123"):
        assert private_value not in result


def test_server_exposes_task_tools_without_prompts_or_resources(tmp_path):
    path = tmp_path / "users.json"
    _write_users(path, [{"name": "Oleg", "is_enable": True}])
    server = create_server(path)

    async def inspect_server():
        async with Client(server) as client:
            tools = await client.list_tools()
            prompts = await client.list_prompts()
            resources = await client.list_resources()
        return tools, prompts, resources

    tools, prompts, resources = asyncio.run(inspect_server())

    assert [tool.name for tool in tools.tools] == [
        "list_enabled_users",
        "get_worklogs",
        "get_git_commits",
    ]
    assert prompts.prompts == []
    assert resources.resources == []


def test_missing_config_returns_safe_tool_error(tmp_path):
    server = create_server(tmp_path / "missing.json")

    async def call_tool():
        async with Client(server) as client:
            return await client.call_tool("list_enabled_users", {})

    result = asyncio.run(call_tool())

    assert result.is_error is True
    assert "missing.json" in str(result.content)
    assert "api_key" not in str(result.content)
