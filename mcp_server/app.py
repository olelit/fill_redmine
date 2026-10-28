from pathlib import Path

from mcp.server import MCPServer

from mcp_server.config import default_users_path
from mcp_server.user_tools import register_user_tools


def create_server(users_path: Path | None = None) -> MCPServer:
    server = MCPServer("Work Assistant")
    register_user_tools(server, users_path if users_path is not None else default_users_path())
    return server
