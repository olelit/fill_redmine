from datetime import date
from pathlib import Path

from clients.git_client import GitClient, GitError
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.config import (
    ProfileConfigError,
    UserProfile,
    default_users_path,
    load_users,
    select_user,
)
from mcp_server.tracker_access import build_user_tracker


def get_worklogs(
    user_name: str, tracker: str, start: str, end: str
) -> list[dict[str, object]]:
    return _get_worklogs(default_users_path(), user_name, tracker, start, end)


def get_git_commits(
    user_name: str, repo_path: str, start: str, end: str
) -> list[dict[str, str]]:
    return _get_git_commits(default_users_path(), user_name, repo_path, start, end)


def register_read_tools(server: MCPServer, users_path: Path) -> None:
    def worklogs(user_name: str, tracker: str, start: str, end: str):
        try:
            return _get_worklogs(users_path, user_name, tracker, start, end)
        except (ProfileConfigError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    def git_commits(user_name: str, repo_path: str, start: str, end: str):
        try:
            return _get_git_commits(users_path, user_name, repo_path, start, end)
        except GitError:
            raise ToolError("Git commit read failed") from None
        except (ProfileConfigError, ValueError) as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(worklogs, name="get_worklogs")
    server.add_tool(git_commits, name="get_git_commits")


def _get_worklogs(
    users_path: Path, user_name: str, tracker: str, start: str, end: str
) -> list[dict[str, object]]:
    if tracker not in ("redmine", "youtrack"):
        raise ProfileConfigError("Unsupported tracker kind")
    start_date, end_date = _date_range(start, end)
    profile = _select_enabled_user(users_path, user_name)
    adapter = build_user_tracker(profile, tracker)
    return [
        {
            "date": item.date,
            "hours": item.hours,
            "description": item.description,
            "issue": item.issue,
            "source": item.source,
        }
        for item in adapter.get_worklogs(start_date, end_date)
    ]


def _get_git_commits(
    users_path: Path, user_name: str, repo_path: str, start: str, end: str
) -> list[dict[str, str]]:
    start_date, end_date = _date_range(start, end)
    profile = _select_enabled_user(users_path, user_name)
    commits = GitClient(repo_path).list_commits(profile.git_email, start_date, end_date)
    return [
        {
            "hash": commit.hash,
            "author_date": commit.date,
            "subject": commit.subject,
            "body": commit.body,
        }
        for commit in commits
    ]


def _select_enabled_user(users_path: Path, user_name: str) -> UserProfile:
    return select_user(load_users(users_path), user_name)


def _date_range(start: str, end: str) -> tuple[date, date]:
    try:
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ProfileConfigError("Dates must use YYYY-MM-DD ISO format") from None
    if start_date.isoformat() != start or end_date.isoformat() != end:
        raise ProfileConfigError("Dates must use YYYY-MM-DD ISO format")
    if start_date > end_date:
        raise ProfileConfigError("Start date must not be after end date")
    return start_date, end_date
