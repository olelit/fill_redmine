from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from clients.ai.factory import create_ai_client
from clients.git_client import GitClient
from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import (
    TrackingReport,
    TrackingRow,
    TrackingSource,
    TrackingWriteResult,
)
from dto.worklog_dto import WorklogDTO
from services.tracking_plan_service import TrackingPlanService
from trackers.base import BaseTracker
from trackers.registry import build_tracker


class TrackingError(RuntimeError):
    pass


class TrackingService:
    def __init__(
        self,
        tracker_builder: Callable[[str, dict], BaseTracker | None] = build_tracker,
        log: Callable[[str], None] = print,
    ) -> None:
        self.tracker_builder = tracker_builder
        self.log = log
        self.git_client_factory = GitClient
        self.ai_client_factory = create_ai_client

    def generate_report(
        self,
        project: ProjectConfig,
        selected_user_ids: list[int],
        destination_kind: str,
        source: TrackingSource,
        source_kind: str,
        start: date,
        end: date,
        ai_settings: Any | None = None,
    ) -> TrackingReport:
        try:
            source = TrackingSource(source)
        except ValueError as exc:
            raise TrackingError(f"Неизвестный источник: {source}") from exc
        if start > end:
            raise TrackingError("Начало периода позже конца")
        if source is TrackingSource.TRACKER and source_kind == destination_kind:
            raise TrackingError("Источник и назначение не могут совпадать")
        users = [user for user in project.users if user.db_id in selected_user_ids]
        if not users:
            raise TrackingError("Не выбран ни один юзер")

        report = TrackingReport(
            destination_kind=destination_kind,
            source=source,
            source_kind=source_kind,
            start=start,
            end=end,
        )
        for user in users:
            try:
                self._add_user_rows(
                    report,
                    project,
                    user,
                    destination_kind,
                    source,
                    source_kind,
                    start,
                    end,
                    ai_settings,
                )
            except Exception as exc:
                report.errors.append(f"{user.name}: {exc}")
        report.rows.sort(key=lambda row: (row.user_name, row.date))
        return report

    def _add_user_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        destination_kind: str,
        source: TrackingSource,
        source_kind: str,
        start: date,
        end: date,
        ai_settings: Any | None,
    ) -> None:
        if user.db_id is None:
            raise TrackingError("У юзера нет id")
        destination = self._tracker(user, destination_kind)
        if not destination.can_write:
            raise TrackingError(
                f"Трекер {destination.label} не поддерживает запись"
            )
        existing = self._existing_by_day(destination, start, end)
        if source is TrackingSource.AUTOFILL:
            self._add_autofill_rows(report, project, user, existing, start, end)
            return
        if source is TrackingSource.TRACKER:
            source_tracker = self._tracker(user, source_kind)
            source_by_day = self._existing_by_day(source_tracker, start, end)
            self._add_tracker_rows(report, project, user, existing, source_by_day, start, end)
            return
        if source is TrackingSource.COMMITS:
            self._add_commits_rows(
                report, project, user, destination_kind, existing, start, end, ai_settings
            )
            return
        raise TrackingError(f"Источник {source.value} пока не поддерживается")

    def _tracker(self, user: ProjectUserConfig, kind: str) -> BaseTracker:
        tracker = self.tracker_builder(kind, user.trackers.get(kind, {}))
        if tracker is None:
            raise TrackingError(f"неизвестный трекер {kind}")
        if not tracker.is_configured():
            raise TrackingError(f"трекер {tracker.label} не настроен")
        return tracker

    @staticmethod
    def _existing_by_day(
        tracker: BaseTracker, start: date, end: date
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for worklog in tracker.get_worklogs(start, end):
            result[worklog.date] = result.get(worklog.date, 0) + worklog.hours
        return result

    def _add_autofill_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        existing: dict[str, float],
        start: date,
        end: date,
    ) -> None:
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            proposed = max(0.0, round(target - existing_hours, 2))
            report.rows.append(
                TrackingRow(
                    row_id=f"{user.db_id}:{iso}",
                    user_id=int(user.db_id),
                    user_name=user.name,
                    date=iso,
                    existing_hours=existing_hours,
                    proposed_hours=proposed,
                    comment=project.default_comment,
                    include=proposed > 0,
                )
            )
            current += timedelta(days=1)

    def _add_tracker_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        existing: dict[str, float],
        source_by_day: dict[str, float],
        start: date,
        end: date,
    ) -> None:
        current = start
        while current <= end:
            iso = current.isoformat()
            proposed = round(source_by_day.get(iso, 0.0), 2)
            report.rows.append(
                TrackingRow(
                    row_id=f"{user.db_id}:{iso}",
                    user_id=int(user.db_id),
                    user_name=user.name,
                    date=iso,
                    existing_hours=round(existing.get(iso, 0.0), 2),
                    proposed_hours=proposed,
                    comment=project.default_comment,
                    source_details=report.source_kind,
                    include=proposed > 0,
                )
            )
            current += timedelta(days=1)

    def write_report(
        self, project: ProjectConfig, report: TrackingReport
    ) -> TrackingWriteResult:
        result = TrackingWriteResult()
        users = {user.db_id: user for user in project.users}
        for user_id, user in users.items():
            rows = [
                row
                for row in report.rows
                if row.user_id == user_id
                and row.include
                and row.proposed_hours > 0
                and not row.error
            ]
            if not rows:
                continue
            try:
                tracker = self._tracker(user, report.destination_kind)
                records = [
                    WorklogDTO(
                        date=row.date,
                        hours=row.proposed_hours,
                        description=row.comment or project.default_comment,
                    )
                    for row in rows
                ]
                errors = tracker.create_worklogs(records)
                errors_by_date = dict(errors)
                for row in rows:
                    if row.date in errors_by_date:
                        row.status = "ошибка"
                        row.error = errors_by_date[row.date]
                        result.errors.append((user.name, row.date, row.error))
                    else:
                        row.status = "записано"
                        row.include = False
                        result.written += 1
            except Exception as exc:
                result.errors.append((user.name, "", str(exc)))
        return result

    def _add_commits_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        destination_kind: str,
        existing: dict[str, float],
        start: date,
        end: date,
        ai_settings: Any | None,
    ) -> None:
        if not project.git_repo_path:
            raise TrackingError("Не задан git-репозиторий проекта")
        if not user.git_email:
            raise TrackingError("Не задан git email юзера")
        if ai_settings is None:
            raise TrackingError("Не настроен AI")
        git = self.git_client_factory(project.git_repo_path)
        commits = git.list_commits(user.git_email, start, end)
        ai_client = self.ai_client_factory(ai_settings)
        plan = TrackingPlanService(ai_client, log=self.log).build_plan(
            project, user, destination_kind, existing, start, end, commits
        )
        for day in plan.days:
            report.rows.append(
                TrackingRow(
                    row_id=f"{user.db_id}:{day.date}",
                    user_id=int(user.db_id),
                    user_name=user.name,
                    date=day.date,
                    existing_hours=day.existing_hours,
                    proposed_hours=day.planned_hours,
                    comment=day.comment or project.default_comment,
                    source_details=",".join(day.commit_hashes),
                    include=day.planned_hours > 0,
                )
            )
