from datetime import date

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import TrackingReport, TrackingRow, TrackingSource
from services.tracking_service import TrackingService
from trackers.base import BaseTracker, TrackerField


class FakeTracker(BaseTracker):
    kind = "fake"
    label = "Fake"
    fields = (TrackerField("token", "Token"),)
    can_write = True

    def __init__(self, config, worklogs=None, failures=None, error=None):
        super().__init__(config)
        self.worklogs = worklogs or []
        self.failures = failures or {}
        self.error = error
        self.written = []

    def get_worklogs(self, start, end):
        return list(self.worklogs)

    def create_worklogs(self, records):
        if self.error is not None:
            raise self.error
        self.written.extend(records)
        return [
            (record.date, self.failures[record.date])
            for record in records
            if record.date in self.failures
        ]


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
                trackers={"fake": {"token": "a"}},
            ),
            ProjectUserConfig(
                name="B",
                db_id=2,
                git_email="b@example.com",
                trackers={"fake": {"token": "b"}},
            ),
        ],
    )
    data.update(overrides)
    return ProjectConfig(**data)


def make_row(**overrides):
    data = dict(
        row_id="1:2026-10-01",
        user_id=1,
        user_name="A",
        date="2026-10-01",
        existing_hours=0.0,
        proposed_hours=8.0,
        comment="development",
    )
    data.update(overrides)
    return TrackingRow(**data)


def make_report(*rows):
    return TrackingReport(
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        rows=list(rows),
    )


def test_write_report_skips_excluded_and_zero_rows():
    tracker = FakeTracker({"token": "a"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    report = make_report(
        make_row(row_id="1:a", date="2026-10-01", include=True),
        make_row(row_id="1:b", date="2026-10-02", include=False),
        make_row(row_id="1:c", date="2026-10-03", proposed_hours=0),
        make_row(row_id="1:d", date="2026-10-04", error="уже с ошибкой"),
    )

    result = service.write_report(project_with_users(), report)

    assert result.written == 1
    assert [record.date for record in tracker.written] == ["2026-10-01"]
    assert [row.status for row in report.rows] == ["записано", "", "", ""]
    assert [row.include for row in report.rows] == [False, False, True, True]


def test_write_report_marks_tracker_day_errors():
    tracker = FakeTracker({"token": "a"}, failures={"2026-10-01": "нет доступа"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    report = make_report(
        make_row(date="2026-10-01"),
        make_row(row_id="1:2", date="2026-10-02"),
    )

    result = service.write_report(project_with_users(), report)

    assert result.written == 1
    assert report.rows[0].status == "ошибка"
    assert report.rows[0].error == "нет доступа"
    assert report.rows[0].include is True
    assert report.rows[1].status == "записано"
    assert result.errors == [("A", "2026-10-01", "нет доступа")]


def test_write_report_uses_default_comment_when_empty():
    tracker = FakeTracker({"token": "a"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    report = make_report(make_row(comment=""))

    service.write_report(project_with_users(), report)

    assert tracker.written[0].description == "development"


def test_write_report_groups_rows_by_user():
    trackers = {}
    service = TrackingService(
        tracker_builder=lambda kind, config: trackers.setdefault(
            config["token"], FakeTracker(config)
        )
    )
    report = make_report(
        make_row(row_id="1:a", date="2026-10-01"),
        make_row(
            row_id="2:b",
            user_id=2,
            user_name="B",
            date="2026-10-02",
        ),
    )

    result = service.write_report(project_with_users(), report)

    assert result.written == 2
    assert [record.date for record in trackers["a"].written] == ["2026-10-01"]
    assert [record.date for record in trackers["b"].written] == ["2026-10-02"]


def test_write_report_reports_missing_tracker_config():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    project = project_with_users(
        users=[ProjectUserConfig(name="A", db_id=1, trackers={})]
    )
    report = make_report(make_row())

    result = service.write_report(project, report)

    assert result.written == 0
    assert result.errors
    assert result.errors[0][0] == "A"
    assert result.errors[0][2]
    assert report.rows[0].status == ""
    assert report.rows[0].include is True
