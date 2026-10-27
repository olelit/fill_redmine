from datetime import date

import pytest

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import TrackingSource
from dto.worklog_dto import WorklogDTO
from services.tracking_service import TrackingError, TrackingService
from trackers.base import BaseTracker, TrackerField


class FakeTracker(BaseTracker):
    kind = "fake"
    label = "Fake"
    fields = (TrackerField("token", "Token"),)
    can_write = True

    def __init__(self, config, worklogs=None):
        super().__init__(config)
        self.worklogs = worklogs or []
        self.written = []

    def get_worklogs(self, start, end):
        return list(self.worklogs)

    def create_worklogs(self, records):
        self.written.extend(records)
        return []


def project_with_users(**overrides):
    data = dict(
        name="P",
        workday_hours=8,
        default_comment="development",
        users=[
            ProjectUserConfig(
                name="A",
                db_id=1,
                git_email="a@example.com",
                trackers={"fake": {"token": "t"}},
            ),
            ProjectUserConfig(
                name="B",
                db_id=2,
                git_email="b@example.com",
                trackers={"fake": {"token": "t"}},
            ),
        ],
    )
    data.update(overrides)
    return ProjectConfig(**data)


def test_autofill_fills_deficit_for_weekdays():
    tracker = FakeTracker(
        {"token": "t"},
        worklogs=[WorklogDTO(date="2026-10-01", hours=3)],
    )
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users()

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert [(r.date, r.existing_hours, r.proposed_hours) for r in report.rows] == [
        ("2026-10-01", 3, 5),
        ("2026-10-02", 0, 8),
    ]
    assert all(r.comment == "development" for r in report.rows)


def test_autofill_excludes_weekend_and_excluded_date():
    tracker = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users(exclude_dates=["2026-10-05"])

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 3),
        end=date(2026, 10, 5),
    )

    assert [r.proposed_hours for r in report.rows] == [0, 0, 0]


def test_tracker_source_copies_all_hours():
    destination = FakeTracker({"token": "t"})
    source = FakeTracker(
        {"token": "t"},
        worklogs=[
            WorklogDTO(date="2026-10-01", hours=4),
            WorklogDTO(date="2026-10-02", hours=6),
        ],
    )
    service = TrackingService(
        tracker_builder=lambda kind, config: source if kind == "source" else destination
    )
    project = project_with_users(
        users=[
            ProjectUserConfig(
                name="A",
                db_id=1,
                trackers={"fake": {"token": "t"}, "source": {"token": "t"}},
            )
        ]
    )

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.TRACKER,
        source_kind="source",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert [r.proposed_hours for r in report.rows] == [4, 6]
    assert all(r.include for r in report.rows)


def test_source_cannot_equal_destination():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))

    with pytest.raises(TrackingError, match="совпадать"):
        service.generate_report(
            project_with_users(),
            selected_user_ids=[1],
            destination_kind="fake",
            source=TrackingSource.TRACKER,
            source_kind="fake",
            start=date(2026, 10, 1),
            end=date(2026, 10, 2),
        )


def test_missing_destination_config_is_reported():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    project = project_with_users(
        users=[ProjectUserConfig(name="A", db_id=1, trackers={})]
    )

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert report.rows == []
    assert any("A" in error for error in report.errors)
