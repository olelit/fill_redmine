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
    tracker = {"redmine": "Redmine", "youtrack": "YouTrack"}.get(
        plan.destination_kind, plan.destination_kind
    )
    if plan.destination_kind == "redmine":
        tracker = f"{tracker} (issue {plan.issue_id})"
    total = sum(entry.hours for entry in plan.entries)
    dates = [entry.date for entry in plan.entries]
    period = f"{min(dates)} — {max(dates)}" if dates else "—"
    lines = [
        f"Записать {len(plan.entries)} worklog'ов на {total:g} ч?",
        f"Пользователь: {plan.user_name}",
        f"Трекер: {tracker}",
        f"Период: {period}",
    ]
    if plan.deletions:
        deleted_hours = sum(deletion.hours for deletion in plan.deletions)
        lines.append(
            f"Будет удалено: {len(plan.deletions)} старых записей "
            f"({deleted_hours:g} ч)"
        )
    lines.extend(
        [
            f"Предупреждений: {len(plan.warnings)}",
            "Подробный план выведен в чате.",
        ]
    )
    return "\n".join(lines)


def _blocked() -> dict[str, object]:
    return {"status": "blocked"}
