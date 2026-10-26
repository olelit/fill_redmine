from datetime import date

import pytest

from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO
from dto.git_commit_dto import GitCommitDTO
from dto.worklog_dto import WorklogDTO
from services.commit_plan_service import CommitPlanService, PlanError
from trackers.base import BaseTracker, TrackerField


class FakeTracker(BaseTracker):
    kind = "fake_plan"
    label = "Fake"
    fields = (TrackerField("token", "Token"),)

    def get_worklogs(self, start, end):
        return [
            WorklogDTO(date="2026-10-01", hours=3),
            WorklogDTO(date="2026-10-02", hours=8),
        ]


class BrokenTracker(BaseTracker):
    kind = "broken_plan"
    label = "Broken"
    fields = (TrackerField("token", "Token"),)

    def get_worklogs(self, start, end):
        raise RuntimeError("tracker down")


class FakeAi:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.payload


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        workday_hours=8.0,
        exclude_dates=[],
        trackers={"fake_plan": {"token": "t"}},
    )
    data.update(overrides)
    return ProjectConfig(**data)


def make_commits() -> list[GitCommitDTO]:
    return [
        GitCommitDTO(
            hash="aaa111",
            author_name="Oleg",
            author_email="oleg@example.com",
            date="2026-10-01T10:00:00+00:00",
            subject="Add import",
        ),
        GitCommitDTO(
            hash="bbb222",
            author_name="Oleg",
            author_email="oleg@example.com",
            date="2026-10-02T10:00:00+00:00",
            subject="Fix tests",
        ),
    ]


def make_service(payload, **overrides) -> CommitPlanService:
    service = CommitPlanService(ai_client=FakeAi(payload), log=lambda message: None)
    service.tracker_builder = lambda kind, config: FakeTracker(config)
    return service


def test_generates_plan_and_caps_hours():
    payload = {
        "summary": "ok",
        "days": [
            {
                "date": "2026-10-01",
                "hours": 4,
                "comment": "Импорт",
                "commit_hashes": ["aaa111", "unknown"],
                "confidence": "high",
            },
            {
                "date": "2026-10-02",
                "hours": 8,
                "comment": "Тесты",
                "commit_hashes": ["bbb222"],
                "confidence": "medium",
            },
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 2),
        ["fake_plan"],
        make_commits(),
    )

    assert isinstance(plan, CommitPlanDTO)
    assert plan.summary == "ok"
    first = plan.days[0]
    assert first.date == "2026-10-01"
    assert first.existing_hours == 3
    assert first.deficit_hours == 5
    assert first.planned_hours == 4
    assert first.commit_hashes == ["aaa111"]
    second = plan.days[1]
    assert second.existing_hours == 8
    assert second.deficit_hours == 0
    assert second.planned_hours == 0


def test_excluded_weekday_has_zero_target():
    payload = {"summary": "ok", "days": []}
    service = make_service(payload)

    plan = service.generate(
        make_project(exclude_dates=["2026-10-05"]),
        date(2026, 10, 5),
        date(2026, 10, 6),
        ["fake_plan"],
        [],
    )

    assert [day.deficit_hours for day in plan.days] == [0, 8]


def test_weekend_has_zero_target():
    payload = {"summary": "ok", "days": []}
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 3),
        date(2026, 10, 4),
        ["fake_plan"],
        [],
    )

    assert [day.deficit_hours for day in plan.days] == [0, 0]


def test_snaps_hours_to_half_and_removes_unknown_hashes():
    payload = {
        "summary": "ok",
        "days": [
            {
                "date": "2026-10-01",
                "hours": 1.3,
                "comment": "x",
                "commit_hashes": ["nope"],
                "confidence": "weird",
            }
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 1),
        ["fake_plan"],
        make_commits(),
    )

    assert plan.days[0].planned_hours == 1.5
    assert plan.days[0].commit_hashes == []
    assert plan.days[0].confidence == "low"


def test_ignores_dates_outside_period():
    payload = {
        "summary": "ok",
        "days": [
            {"date": "2026-09-01", "hours": 4, "comment": "x"},
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 1),
        ["fake_plan"],
        [],
    )

    assert all(day.date != "2026-09-01" for day in plan.days)
    assert plan.days[0].planned_hours == 0


def test_requires_selected_tracker():
    service = make_service({"summary": "ok", "days": []})

    with pytest.raises(PlanError, match="трекер"):
        service.generate(
            make_project(), date(2026, 10, 1), date(2026, 10, 1), [], []
        )


def test_tracker_failure_aborts():
    service = make_service({"summary": "ok", "days": []})
    service.tracker_builder = lambda kind, config: BrokenTracker(config)

    with pytest.raises(PlanError, match="Broken"):
        service.generate(
            make_project(trackers={"broken_plan": {"token": "t"}}),
            date(2026, 10, 1),
            date(2026, 10, 1),
            ["broken_plan"],
            [],
        )


def test_prompt_contains_commits_and_deficit():
    ai = FakeAi({"summary": "ok", "days": []})
    service = CommitPlanService(ai_client=ai, log=lambda message: None)
    service.tracker_builder = lambda kind, config: FakeTracker(config)

    service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 2),
        ["fake_plan"],
        make_commits(),
    )

    _, user_prompt = ai.calls[0]
    assert "Проект" in user_prompt
    assert "Add import" in user_prompt
    assert '"deficit_hours": 5.0' in user_prompt
