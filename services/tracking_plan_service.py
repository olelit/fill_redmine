import json
from collections.abc import Callable
from datetime import date, timedelta

from clients.ai.base import AiClient
from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from dto.git_commit_dto import GitCommitDTO

SYSTEM_PROMPT = """Ты — ассистент по учёту рабочего времени.
Верни ТОЛЬКО JSON-объект:
{"summary": "итог", "days": [{"date": "YYYY-MM-DD", "hours": 0.0,
"comment": "кратко", "commit_hashes": ["hash"], "confidence": "high|medium|low"}]}
Правила: используй только переданные коммиты и хеши; не придумывай работу без
коммитов; часы не больше deficit_hours и кратны 0.5; комментарии по-русски.
"""

MAX_PERIOD_DAYS = 62
MAX_COMMITS_PER_DAY = 20
MAX_COMMIT_BODY_CHARS = 300
CONFIDENCE_LEVELS = {"high", "medium", "low"}


class TrackingPlanError(RuntimeError):
    pass


class TrackingPlanService:
    def __init__(
        self, ai_client: AiClient, log: Callable[[str], None] = print
    ) -> None:
        self.ai_client = ai_client
        self.log = log

    def build_plan(
        self,
        project: ProjectConfig,
        user: ProjectUserConfig,
        destination_kind: str,
        existing: dict[str, float],
        start: date,
        end: date,
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        period_days = (end - start).days + 1
        if period_days > MAX_PERIOD_DAYS:
            raise TrackingPlanError(
                f"Слишком длинный период: {period_days} дней, "
                f"максимум {MAX_PERIOD_DAYS}"
            )
        days: list[DayPlanDTO] = []
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            days.append(
                DayPlanDTO(
                    date=iso,
                    existing_hours=existing_hours,
                    deficit_hours=max(0.0, round(target - existing_hours, 2)),
                    planned_hours=0.0,
                )
            )
            current += timedelta(days=1)

        if not commits:
            for day in days:
                day.comment = "нет коммитов"
            return CommitPlanDTO(summary="", days=days, raw_response="")

        commits_by_date: dict[str, list[GitCommitDTO]] = {}
        for commit in commits:
            commits_by_date.setdefault(commit.date[:10], []).append(commit)

        payload = {
            "project": project.name,
            "user": user.name,
            "destination": destination_kind,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "days": [
                {
                    "date": day.date,
                    "existing_hours": day.existing_hours,
                    "deficit_hours": day.deficit_hours,
                    "commits": [
                        {
                            "hash": commit.hash,
                            "subject": commit.subject,
                            "body": commit.body[:MAX_COMMIT_BODY_CHARS],
                        }
                        for commit in commits_by_date.get(day.date, [])[
                            :MAX_COMMITS_PER_DAY
                        ]
                    ],
                }
                for day in days
            ],
        }
        raw = self.ai_client.complete_json(
            SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return self._apply(days, raw, commits)

    def _apply(
        self,
        days: list[DayPlanDTO],
        raw: dict,
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        by_date = {day.date: day for day in days}
        commits_by_date: dict[str, list[GitCommitDTO]] = {}
        for commit in commits:
            commits_by_date.setdefault(commit.date[:10], []).append(commit)
        known = {commit.hash for commit in commits}
        items = raw.get("days", [])
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            day = by_date.get(str(item.get("date", "")))
            if day is None:
                continue
            if not commits_by_date.get(day.date):
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
            accepted = (
                [h for h in hashes if isinstance(h, str) and h in known]
                if isinstance(hashes, list)
                else []
            )
            day.commit_hashes = list(dict.fromkeys(accepted))
            confidence = str(item.get("confidence", "low")).lower()
            day.confidence = (
                confidence if confidence in CONFIDENCE_LEVELS else "low"
            )
        return CommitPlanDTO(
            summary=str(raw.get("summary", "")).strip(),
            days=days,
            raw_response=json.dumps(raw, ensure_ascii=False),
        )
