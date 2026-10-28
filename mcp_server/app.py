from collections.abc import Callable
from pathlib import Path

from mcp.server import MCPServer

from mcp_server.config import default_users_path
from mcp_server.plans import PlanStore, WritePlan
from mcp_server.read_tools import register_read_tools
from mcp_server.user_tools import register_user_tools
from mcp_server.write_tools import register_write_tool
from mcp_server.writer import execute_plan


def create_server(
    users_path: Path | None = None,
    *,
    write_store: PlanStore | None = None,
    write_executor: Callable[[WritePlan], dict[str, object]] | None = None,
) -> MCPServer:
    server = MCPServer("Work Assistant")
    resolved_users_path = users_path if users_path is not None else default_users_path()
    register_user_tools(server, resolved_users_path)
    register_read_tools(server, resolved_users_path)
    store = write_store if write_store is not None else PlanStore()
    executor = (
        write_executor
        if write_executor is not None
        else lambda plan: execute_plan(plan, resolved_users_path)
    )
    register_write_tool(server, store, executor)
    return server
