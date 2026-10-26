import sqlite3

import pytest

from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        git_repo_path="/tmp/repo",
        git_author_email="me@example.com",
        workday_hours=8.0,
        exclude_dates=["2026-10-05"],
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            },
            "youtrack": {"access_token": "token"},
        },
        ai={
            "base_url": "https://api.example/v1",
            "model": "model",
            "api_key": "ai-key",
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


@pytest.fixture
def repo(tmp_path):
    return ProjectRepository(db_path=tmp_path / "test.db")


def test_list_projects_returns_empty_for_new_db(repo):
    assert repo.list_projects() == []


def test_add_and_list_roundtrip(repo):
    db_id = repo.add_project(make_project())

    projects = repo.list_projects()

    assert db_id == 1
    assert len(projects) == 1
    assert projects[0].name == "Проект"
    assert projects[0].git_repo_path == "/tmp/repo"
    assert projects[0].git_author_email == "me@example.com"
    assert projects[0].workday_hours == 8.0
    assert projects[0].exclude_dates == ["2026-10-05"]
    assert projects[0].trackers["redmine"]["issue_id"] == 2682
    assert projects[0].trackers["youtrack"]["access_token"] == "token"
    assert projects[0].ai["model"] == "model"
    assert projects[0].db_id == db_id


def test_get_project_returns_none_for_missing(repo):
    assert repo.get_project(999) is None


def test_find_by_name(repo):
    repo.add_project(make_project(name="Alpha"))

    assert repo.find_by_name("Alpha").db_id == 1
    assert repo.find_by_name("Missing") is None


def test_update_changes_fields(repo):
    db_id = repo.add_project(make_project())

    repo.update_project(db_id, make_project(name="Beta", workday_hours=7.5))

    project = repo.get_project(db_id)
    assert project.name == "Beta"
    assert project.workday_hours == 7.5


def test_update_missing_raises(repo):
    with pytest.raises(ValueError):
        repo.update_project(999, make_project())


def test_delete_project(repo):
    db_id = repo.add_project(make_project())

    repo.delete_project(db_id)

    assert repo.list_projects() == []


def test_duplicate_name_raises(repo):
    repo.add_project(make_project(name="Alpha"))

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_project(make_project(name="Alpha"))


def test_add_projects_inserts_multiple(repo):
    repo.add_projects([make_project(name="Alpha"), make_project(name="Beta")])

    assert [p.name for p in repo.list_projects()] == ["Alpha", "Beta"]


def test_meta_roundtrip(repo):
    assert repo.get_meta("missing") is None

    repo.set_meta("legacy_users_migrated", "1")

    assert repo.get_meta("legacy_users_migrated") == "1"
