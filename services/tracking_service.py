from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import (
    TrackingReport,
    TrackingRow,
    TrackingSource,
    TrackingWriteResult,
)
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
        destination = self._tracker(user, destination_kind)
        existing = self._existing_by_day(destination, start, end)
        if source is TrackingSource.AUTOFILL:
            self._add_autofill_rows(report, project, user, existing, start, end)
            return
        if source is TrackingSource.TRACKER:
            source_tracker = self._tracker(user, source_kind)
            source_by_day = self._existing_by_day(source_tracker, start, end)
            self._add_tracker_rows(report, project, user, existing, source_by_day, start, end)
            return
        raise TrackingError(f"Источник {source} пока не поддерживается")

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
        raise NotImplementedError
