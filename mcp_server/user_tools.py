from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.config import ProfileConfigError, default_users_path, load_users


def list_enabled_users() -> list[dict[str, str]]:
    return _list_enabled_users(default_users_path())


def register_user_tools(server: MCPServer, users_path: Path) -> None:
    def list_users() -> list[dict[str, str]]:
        try:
            return _list_enabled_users(users_path)
        except ProfileConfigError as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(list_users, name="list_enabled_users")


def _list_enabled_users(users_path: Path) -> list[dict[str, str]]:
    return [
        {
            "name": user.name,
            "trackers": ", ".join(
                tracker for tracker in ("redmine", "youtrack") if getattr(user, tracker)
            ),
        }
        for user in load_users(users_path)
        if user.is_enable
    ]
