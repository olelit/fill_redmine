import json
from datetime import date

import pytest

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.git_commit_dto import GitCommitDTO
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


def test_source_accepts_plain_string():
    source = FakeTracker(
        {"token": "t"},
        worklogs=[WorklogDTO(date="2026-10-01", hours=4)],
    )
    service = TrackingService(
        tracker_builder=lambda kind, config: source if kind == "source" else FakeTracker(config)
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
        source="tracker",
        source_kind="source",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
    )

    assert report.errors == []
    assert [(r.date, r.proposed_hours) for r in report.rows] == [("2026-10-01", 4)]


def test_tracker_source_keeps_destination_existing_hours():
    destination = FakeTracker(
        {"token": "t"},
        worklogs=[WorklogDTO(date="2026-10-01", hours=2)],
    )
    source = FakeTracker(
        {"token": "t"},
        worklogs=[WorklogDTO(date="2026-10-01", hours=4)],
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
        end=date(2026, 10, 1),
    )

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.existing_hours == 2
    assert row.proposed_hours == 4


def test_one_user_error_does_not_block_another():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    project = project_with_users(
        users=[
            ProjectUserConfig(name="A", db_id=1, trackers={}),
            ProjectUserConfig(name="B", db_id=2, trackers={"fake": {"token": "t"}}),
        ]
    )

    report = service.generate_report(
        project,
        selected_user_ids=[1, 2],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert report.rows
    assert all(row.user_name == "B" for row in report.rows)
    assert any("A" in error for error in report.errors)


class ReadOnlyTracker(FakeTracker):
    can_write = False


def test_destination_must_support_write():
    service = TrackingService(tracker_builder=lambda kind, config: ReadOnlyTracker(config))

    report = service.generate_report(
        project_with_users(),
        selected_user_ids=[1, 2],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert report.rows == []
    assert report.errors
    assert all("не поддерживает запись" in error for error in report.errors)


class FakeAi:
    def __init__(self, plan):
        self.plan = plan
        self.calls = 0
        self.last_prompt = ""

    def complete_json(self, system_prompt, user_prompt):
        self.calls += 1
        self.last_prompt = user_prompt
        return self.plan


class FakeGit:
    def __init__(self, commits):
        self.commits = commits

    def list_commits(self, email, start, end):
        return list(self.commits)


def test_commits_source_uses_ai_plan(monkeypatch):
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit(
        [
            GitCommitDTO(
                hash="abc",
                author_name="A",
                author_email="a@example.com",
                date="2026-10-01T10:00:00+00:00",
                subject="Add feature",
            )
        ]
    )
    service.ai_client_factory = lambda settings: FakeAi(
        {
            "summary": "ok",
            "days": [
                {
                    "date": "2026-10-01",
                    "hours": 4,
                    "comment": "Сделал фичу",
                    "commit_hashes": ["abc"],
                    "confidence": "high",
                }
            ],
        }
    )
    project = project_with_users(git_repo_path="/repo")

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    assert report.rows[0].proposed_hours == 4
    assert report.rows[0].comment == "Сделал фичу"


def test_commits_source_clamps_hours_and_drops_unknown_hashes():
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit(
        [
            GitCommitDTO(
                hash="abc",
                author_name="A",
                author_email="a@example.com",
                date="2026-10-01T10:00:00+00:00",
                subject="Add feature",
            )
        ]
    )
    service.ai_client_factory = lambda settings: FakeAi(
        {
            "days": [
                {
                    "date": "2026-10-01",
                    "hours": 20,
                    "comment": "",
                    "commit_hashes": ["zzz", "abc"],
                    "confidence": "extreme",
                }
            ],
        }
    )

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    row = report.rows[0]
    assert row.proposed_hours == 8
    assert row.source_details == "abc"
    assert row.comment == "development"


def test_commits_source_rounds_hours_to_half():
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit(
        [
            GitCommitDTO(
                hash="abc",
                author_name="A",
                author_email="a@example.com",
                date="2026-10-01T10:00:00+00:00",
                subject="Add feature",
            )
        ]
    )
    service.ai_client_factory = lambda settings: FakeAi(
        {"days": [{"date": "2026-10-01", "hours": 3.7}]}
    )

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    assert report.rows[0].proposed_hours == 3.5


def test_commits_source_reports_setup_errors():
    service = TrackingService(
        tracker_builder=lambda kind, config: FakeTracker(config)
    )

    report = service.generate_report(
        project_with_users(),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    assert report.rows == []
    assert any("git-репозиторий" in error for error in report.errors)


def test_commits_source_reports_missing_ai_settings():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    service.git_client_factory = lambda path: FakeGit([])

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=None,
    )

    assert report.rows == []
    assert any("AI" in error for error in report.errors)


def test_commits_source_reports_missing_git_email():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    service.git_client_factory = lambda path: FakeGit([])

    report = service.generate_report(
        project_with_users(
            git_repo_path="/repo",
            users=[
                ProjectUserConfig(
                    name="A",
                    db_id=1,
                    git_email="",
                    trackers={"fake": {"token": "t"}},
                )
            ],
        ),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    assert report.rows == []
    assert any("git email" in error for error in report.errors)


def test_commits_source_ignores_ai_hours_for_day_without_commits():
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit(
        [
            GitCommitDTO(
                hash="abc",
                author_name="A",
                author_email="a@example.com",
                date="2026-10-01T10:00:00+00:00",
                subject="Add feature",
            )
        ]
    )
    service.ai_client_factory = lambda settings: FakeAi(
        {
            "days": [
                {"date": "2026-10-01", "hours": 4, "commit_hashes": ["abc"]},
                {"date": "2026-10-02", "hours": 8, "commit_hashes": []},
            ]
        }
    )

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
        ai_settings=object(),
    )

    by_date = {row.date: row for row in report.rows}
    assert by_date["2026-10-01"].proposed_hours == 4
    assert by_date["2026-10-02"].proposed_hours == 0
    assert by_date["2026-10-02"].include is False


def test_commits_source_without_commits_skips_ai():
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit([])
    ai = FakeAi({"days": [{"date": "2026-10-01", "hours": 8}]})
    service.ai_client_factory = lambda settings: ai

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
        ai_settings=object(),
    )

    assert ai.calls == 0
    assert [row.proposed_hours for row in report.rows] == [0, 0]
    assert [row.comment for row in report.rows] == ["нет коммитов", "нет коммитов"]


def test_commits_source_rejects_period_longer_than_limit():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    service.git_client_factory = lambda path: FakeGit([])
    service.ai_client_factory = lambda settings: FakeAi({"days": []})

    report = service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 1, 1),
        end=date(2026, 3, 10),
        ai_settings=object(),
    )

    assert report.rows == []
    assert any("период" in error.lower() for error in report.errors)


def test_commits_source_caps_commits_and_truncates_bodies():
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    commits = [
        GitCommitDTO(
            hash=f"h{index:02d}",
            author_name="A",
            author_email="a@example.com",
            date="2026-10-01T10:00:00+00:00",
            subject=f"Commit {index}",
            body="x" * 500,
        )
        for index in range(21)
    ]
    service.git_client_factory = lambda path: FakeGit(commits)
    ai = FakeAi({"days": []})
    service.ai_client_factory = lambda settings: ai

    service.generate_report(
        project_with_users(git_repo_path="/repo"),
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    payload = json.loads(ai.last_prompt)
    sent = payload["days"][0]["commits"]
    assert len(sent) == 20
    assert len({commit["hash"] for commit in sent}) == 20
    assert all(len(commit["body"]) <= 300 for commit in sent)


def test_write_report_writes_only_included_rows():
    tracker = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users()
    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
    )
    report.rows[0].proposed_hours = 5
    report.rows[0].comment = "dev"
    report.rows[0].include = True

    result = service.write_report(project, report)

    assert result.written == 1
    assert tracker.written[0].hours == 5
    assert report.rows[0].status == "записано"
    assert report.rows[0].include is False
