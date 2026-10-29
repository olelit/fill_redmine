import json
from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import BaseModel

from mcp_server.plans import PlanError, PlanStore, WritePlan


class _Approval(BaseModel):
    approved: bool


def register_write_tool(
    server: MCPServer,
    store: PlanStore,
    execute: Callable[[WritePlan], dict[str, object]],
) -> None:
    async def write_plan(plan_id: str, ctx: Context) -> dict[str, object]:
        try:
            plan = store.claim(plan_id)
        except PlanError:
            return _blocked()

        try:
            response = await ctx.elicit(_approval_message(plan), _Approval)
        except Exception:
            return _blocked()

        if response.action != "accept" or response.data.approved is not True:
            return _blocked()

        try:
            store.validate_fresh(plan)
        except PlanError:
            return _blocked()

        return execute(plan)

    server.add_tool(write_plan, name="write_plan")


def _approval_message(plan: WritePlan) -> str:
    payload = {
        "user": plan.user_name,
        "tracker": plan.destination_kind,
        "issue": plan.issue_id,
        "entries": [
            {"date": entry.date, "hours": entry.hours, "comment": entry.comment}
            for entry in plan.entries
        ],
    }
    return "Approve writing this worklog plan?\n" + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _blocked() -> dict[str, object]:
    return {"status": "blocked"}
