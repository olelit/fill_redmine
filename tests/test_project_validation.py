from datetime import date

from gui.project_validation import parse_period, validate_project_form


def test_valid_project_form():
    project, errors = validate_project_form(
        form={"name": "Проект", "git_repo_path": "/tmp/repo", "git_author_email": "me@example.com", "workday_hours": "8"},
        exclude_dates=["2026-10-05"],
        tracker_values={
            "redmine": {
                "api_key": "key",
                "user_id": "16",
                "activity_id": "9",
                "issue_id": "2682",
                "comment": "dev",
            }
        },
        ai_values={"base_url": "https://api.example/v1", "model": "m", "api_key": "k"},
    )

    assert errors == []
    assert project.name == "Проект"
    assert project.workday_hours == 8.0
    assert project.trackers["redmine"]["user_id"] == 16
    assert project.ai["model"] == "m"


def test_empty_name_is_rejected():
    project, errors = validate_project_form(
        form={"name": " ", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={},
        ai_values={},
    )

    assert project is None
    assert "Имя проекта обязательно" in errors


def test_bad_workday_is_rejected():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "25"},
        exclude_dates=[],
        tracker_values={},
        ai_values={},
    )

    assert project is None
    assert any("рабочий день" in error.lower() for error in errors)


def test_partial_tracker_is_rejected():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={"redmine": {"api_key": "key"}},
        ai_values={},
    )

    assert project is None
    assert any("Redmine" in error for error in errors)


def test_empty_tracker_is_allowed():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={"redmine": {}},
        ai_values={},
    )

    assert errors == []
    assert project.trackers == {}


def test_parse_period():
    start, end = parse_period("2026-10-01", "2026-10-31")
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)


def test_parse_period_rejects_reverse_order():
    try:
        parse_period("2026-10-31", "2026-10-01")
    except ValueError as exc:
        assert "позже" in str(exc)
    else:
        raise AssertionError("expected ValueError")
