from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from pydantic import BaseModel

from mcp_server.plans import PlanError, PlanStore, WritePlan, plan_entry_issue


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
    total = sum(entry.hours for entry in plan.entries)
    lines = [
        "Подтверждение записи worklog'ов",
        f"Пользователь: {_one_line(plan.user_name)}",
        f"Трекер: {tracker}",
        f"Строк: {len(plan.entries)}, всего: {total:g} ч",
        "",
    ]
    last_date = ""
    for entry in plan.entries:
        if entry.date != last_date:
            if last_date:
                lines.append("")
            lines.append(entry.date)
            last_date = entry.date
        issue = _one_line(plan_entry_issue(plan, entry))
        comment = _one_line(entry.comment)
        lines.append(f"  {entry.hours:g} ч  {issue}  {comment}")
    if plan.warnings:
        lines.extend(["", "Предупреждения:"])
        lines.extend(f"- {_one_line(warning)}" for warning in plan.warnings)
    lines.extend(["", "Записать эти worklog'и? Поставьте галочку подтверждения."])
    return "\n".join(lines)


def _one_line(value: object) -> str:
    return " ".join(str(value).split()).replace("|", "/")


def _blocked() -> dict[str, object]:
    return {"status": "blocked"}
