from configs.project_config import ProjectUserConfig
from gui.settings_validation import (
    duplicate_user_names,
    validate_project_settings,
    validate_user_settings,
)


def test_project_settings_valid():
    project, errors = validate_project_settings(
        {"git_repo_path": "/repo", "workday_hours": "8", "default_comment": "development"},
        exclude_dates=["2026-10-05"],
    )
    assert errors == []
    assert project.workday_hours == 8
    assert project.default_comment == "development"
    assert project.git_repo_path == "/repo"
    assert project.exclude_dates == ["2026-10-05"]


def test_project_settings_reject_empty_comment():
    project, errors = validate_project_settings(
        {"workday_hours": "8", "default_comment": ""}, []
    )
    assert project is None
    assert any("комментарий" in error.lower() for error in errors)


def test_project_settings_reject_bad_workday():
    project, errors = validate_project_settings(
        {"workday_hours": "abc", "default_comment": "development"}, []
    )
    assert project is None
    assert any("рабочий день" in error.lower() for error in errors)


def test_project_settings_reject_workday_out_of_range():
    project, errors = validate_project_settings(
        {"workday_hours": "25", "default_comment": "development"}, []
    )
    assert project is None
    assert any("рабочий день" in error.lower() for error in errors)


def test_project_settings_sort_exclude_dates():
    project, errors = validate_project_settings(
        {"workday_hours": "7.5", "default_comment": "dev"},
        exclude_dates=["2026-10-05", "2026-10-01"],
    )
    assert errors == []
    assert project.workday_hours == 7.5
    assert project.exclude_dates == ["2026-10-01", "2026-10-05"]


def test_user_settings_valid():
    user, errors = validate_user_settings(
        "Олег",
        "me@example.com",
        {"redmine": {"api_key": "key", "user_id": "16", "activity_id": "9", "issue_id": "2682"}},
    )
    assert errors == []
    assert user.name == "Олег"
    assert user.git_email == "me@example.com"
    assert user.trackers["redmine"]["user_id"] == 16
    assert user.trackers["redmine"]["api_key"] == "key"


def test_user_settings_partial_tracker_rejected():
    user, errors = validate_user_settings(
        "Олег", "", {"redmine": {"api_key": "key"}}
    )
    assert user is None
    assert any("Redmine" in error for error in errors)


def test_user_settings_empty_tracker_is_allowed():
    user, errors = validate_user_settings("Олег", "", {"redmine": {}})
    assert errors == []
    assert user.trackers == {}


def test_user_settings_requires_name():
    user, errors = validate_user_settings("  ", "", {})
    assert user is None
    assert any("имя" in error.lower() for error in errors)


def test_user_settings_rejects_bad_git_email():
    user, errors = validate_user_settings("Олег", "not-an-email", {})
    assert user is None
    assert any("email" in error.lower() for error in errors)


def test_user_settings_rejects_bad_int():
    user, errors = validate_user_settings(
        "Олег",
        "",
        {"redmine": {"api_key": "key", "user_id": "abc", "activity_id": "9", "issue_id": "2682"}},
    )
    assert user is None
    assert any("user_id" in error for error in errors)


def test_duplicate_user_names():
    users = [
        ProjectUserConfig(name="Олег"),
        ProjectUserConfig(name="Аня"),
        ProjectUserConfig(name="Олег"),
    ]
    assert duplicate_user_names(users) == ["Олег"]


def test_duplicate_user_names_returns_empty_for_unique():
    users = [ProjectUserConfig(name="Олег"), ProjectUserConfig(name="Аня")]
    assert duplicate_user_names(users) == []
