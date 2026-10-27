import sqlite3

import pytest

from configs.project_config import ProjectConfig, ProjectUserConfig
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


def make_user(name="Олег", **overrides) -> ProjectUserConfig:
    data = dict(
        name=name,
        git_email=f"{name.lower()}@example.com",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
            },
            "youtrack": {"access_token": "token", "issue_id": "PROJ-1"},
        },
    )
    data.update(overrides)
    return ProjectUserConfig(**data)


def test_project_users_roundtrip(repo):
    db_id = repo.add_project(make_project(users=[make_user()]))

    project = repo.get_project(db_id)

    assert project.default_comment == "development"
    assert len(project.users) == 1
    assert project.users[0].name == "Олег"
    assert project.users[0].trackers["youtrack"]["issue_id"] == "PROJ-1"


def test_add_update_delete_user(repo):
    project_id = repo.add_project(make_project())
    user_id = repo.add_user(project_id, make_user("Первый"))

    repo.update_user(user_id, make_user("Второй", git_email="new@example.com"))
    assert repo.list_users(project_id)[0].name == "Второй"
    assert repo.list_users(project_id)[0].git_email == "new@example.com"

    repo.delete_user(user_id)
    assert repo.list_users(project_id) == []


def test_replace_users_replaces_all(repo):
    project_id = repo.add_project(make_project(users=[make_user("Старый")]))

    repo.replace_users(project_id, [make_user("Новый")])

    assert [user.name for user in repo.list_users(project_id)] == ["Новый"]


def test_merge_users_from_updates_and_adds(repo):
    target_id = repo.add_project(make_project(name="Target", users=[make_user("Олег")]))
    donor = make_project(
        name="Donor",
        git_repo_path="/donor/repo",
        workday_hours=7.5,
        default_comment="donor",
        users=[
            make_user("Олег", git_email="updated@example.com"),
            make_user("Новый"),
        ],
    )
    donor_id = repo.add_project(donor)
    donor = repo.get_project(donor_id)

    repo.merge_users_from(target_id, donor)

    target = repo.get_project(target_id)
    assert target.git_repo_path == "/donor/repo"
    assert target.workday_hours == 7.5
    assert target.default_comment == "donor"
    assert [user.name for user in target.users] == ["Олег", "Новый"]
    assert target.users[0].git_email == "updated@example.com"
