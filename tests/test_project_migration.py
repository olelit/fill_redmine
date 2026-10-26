from configs.user_config import UserConfig
from storage.migration import migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


def make_user(**overrides) -> UserConfig:
    data = dict(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="youtrack",
        youtrack_access_token="token",
        exclude_dates=["2026-10-05"],
    )
    data.update(overrides)
    return UserConfig(**data)


def make_repos(tmp_path):
    db_path = tmp_path / "test.db"
    return (
        ProjectRepository(db_path=db_path),
        UserRepository(db_path=db_path),
    )


def test_migrates_user_fields_to_project(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user())

    count = migrate_users_to_projects(
        project_repo, user_repo, log=lambda message: None
    )

    assert count == 1
    project = project_repo.list_projects()[0]
    assert project.name == "Олег"
    assert project.exclude_dates == ["2026-10-05"]
    assert project.trackers["redmine"] == {
        "api_key": "key",
        "user_id": 16,
        "activity_id": 9,
        "issue_id": 2682,
        "comment": "development",
    }
    assert project.trackers["youtrack"] == {"access_token": "token"}
    assert project_repo.get_meta("legacy_users_migrated") == "1"


def test_manual_user_gets_only_redmine_tracker(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user(driver="manual", youtrack_access_token=""))

    migrate_users_to_projects(project_repo, user_repo, log=lambda message: None)

    project = project_repo.list_projects()[0]
    assert "redmine" in project.trackers
    assert "youtrack" not in project.trackers


def test_migration_is_idempotent(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user())

    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 1
    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 0
    assert len(project_repo.list_projects()) == 1


def test_duplicate_names_get_suffix(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_users([make_user(), make_user(user_id=17)])

    migrate_users_to_projects(project_repo, user_repo, log=lambda message: None)

    assert [p.name for p in project_repo.list_projects()] == ["Олег", "Олег (2)"]


def test_no_users_does_not_mark_migration(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)

    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 0
    assert project_repo.get_meta("legacy_users_migrated") is None
