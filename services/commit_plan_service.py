import json
from collections.abc import Callable
from datetime import date, timedelta

from clients.ai_client import AiClient
from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from dto.git_commit_dto import GitCommitDTO
from trackers.base import BaseTracker
from trackers.registry import build_tracker

SYSTEM_PROMPT = """Ты — ассистент по учёту рабочего времени.
Верни ТОЛЬКО JSON-объект без markdown:
{"summary": "краткий итог", "days": [{"date": "YYYY-MM-DD", "hours": 0.0,
"comment": "краткое описание работы", "commit_hashes": ["hash"],
"confidence": "high|medium|low"}]}
Правила:
- используй только переданные коммиты и их хеши;
- не придумывай работу, если коммитов за день нет — верни 0 часов;
- комментарии пиши по-русски, кратко и по делу;
- часы не больше deficit_hours и кратны 0.5;
- предлагай часы только на дни с положительным deficit_hours.
"""


class PlanError(RuntimeError):
    pass


class CommitPlanService:
    def __init__(
        self,
        ai_client: AiClient,
        tracker_builder: Callable[[str, dict], BaseTracker | None] = build_tracker,
        log: Callable[[str], None] = print,
    ) -> None:
        self.ai_client = ai_client
        self.tracker_builder = tracker_builder
        self.log = log

    def generate(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        selected_kinds: list[str],
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        if start > end:
            raise PlanError("Начало периода позже конца")
        if not selected_kinds:
            raise PlanError("Выберите хотя бы один трекер")

        existing = self._collect_existing(project, start, end, selected_kinds)
        days = self._build_days(project, start, end, existing)
        payload = {
            "project": project.name,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "workday_hours": project.workday_hours,
            "days": [
                {
                    "date": day.date,
                    "target_hours": (
                        project.workday_hours
                        if date.fromisoformat(day.date).weekday() < 5
                        and day.date not in project.exclude_dates
                        else 0.0
                    ),
                    "existing_hours": day.existing_hours,
                    "deficit_hours": day.deficit_hours,
                    "commits": [
                        {
                            "hash": commit.hash,
                            "subject": commit.subject,
                            "body": commit.body[:1000],
                        }
                        for commit in commits
                        if commit.date[:10] == day.date
                    ],
                }
                for day in days
            ],
        }
        raw = self.ai_client.complete_json(
            SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        return self._apply_ai_response(days, raw, commits)

    def _collect_existing(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        selected_kinds: list[str],
    ) -> dict[str, float]:
        existing: dict[str, float] = {}
        for kind in selected_kinds:
            tracker = self.tracker_builder(
                kind, project.trackers.get(kind, {})
            )
            if tracker is None:
                raise PlanError(f"Неизвестный трекер: {kind}")
            if not tracker.is_configured():
                raise PlanError(f"Трекер {tracker.label} не настроен")
            try:
                worklogs = tracker.get_worklogs(start, end)
            except Exception as exc:
                raise PlanError(f"Трекер {tracker.label}: {exc}") from exc
            for worklog in worklogs:
                existing[worklog.date] = (
                    existing.get(worklog.date, 0) + worklog.hours
                )
        return existing

    def _build_days(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        existing: dict[str, float],
    ) -> list[DayPlanDTO]:
        result: list[DayPlanDTO] = []
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            deficit = max(0.0, round(target - existing_hours, 2))
            result.append(
                DayPlanDTO(
                    date=iso,
                    existing_hours=existing_hours,
                    deficit_hours=deficit,
                    planned_hours=0.0,
                )
            )
            current += timedelta(days=1)
        return result

    def _apply_ai_response(
        self,
        days: list[DayPlanDTO],
        raw: dict,
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        by_date = {day.date: day for day in days}
        known_hashes = {commit.hash for commit in commits}
        for item in raw.get("days", []):
            if not isinstance(item, dict):
                continue
            day = by_date.get(str(item.get("date", "")))
            if day is None:
                self.log(f"ИИ вернул дату вне периода: {item.get('date')}")
                continue
            try:
                hours = float(item.get("hours", 0))
            except (TypeError, ValueError):
                continue
            hours = round(hours * 2) / 2
            max_half = int(day.deficit_hours * 2) / 2
            day.planned_hours = max(0.0, min(hours, max_half))
            day.comment = str(item.get("comment", "")).strip()
            hashes = item.get("commit_hashes", [])
            day.commit_hashes = (
                [
                    value
                    for value in hashes
                    if isinstance(value, str) and value in known_hashes
                ]
                if isinstance(hashes, list)
                else []
            )
            confidence = str(item.get("confidence", "low")).lower()
            day.confidence = (
                confidence
                if confidence in {"high", "medium", "low"}
                else "low"
            )

        return CommitPlanDTO(
            summary=str(raw.get("summary", "")).strip(),
            days=days,
            raw_response=json.dumps(raw, ensure_ascii=False),
        )
