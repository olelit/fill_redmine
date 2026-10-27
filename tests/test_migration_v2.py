from configs.project_config import ProjectConfig
from configs.ai_settings import AiSettings
from storage.migration import migrate_projects_to_v2
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


def test_migrates_legacy_project_to_user_and_ai(tmp_path):
    db_path = tmp_path / "test.db"
    project_repo = ProjectRepository(db_path=db_path)
    settings_repo = SettingsRepository(db_path=db_path)
    project_id = project_repo.add_project(
        ProjectConfig(
            name="Старый",
            git_author_email="me@example.com",
            trackers={"redmine": {"api_key": "key", "user_id": 16,
                                  "activity_id": 9, "issue_id": 2682}},
            ai={"base_url": "https://ai.example/v1", "model": "old", "api_key": "ai-key"},
        )
    )

    count = migrate_projects_to_v2(project_repo, settings_repo, log=lambda m: None)

    project = project_repo.get_project(project_id)
    assert count == 1
    assert len(project.users) == 1
    assert project.users[0].name == "Старый"
    assert project.users[0].git_email == "me@example.com"
    assert project.users[0].trackers["redmine"]["issue_id"] == 2682
    settings = settings_repo.get_ai_settings()
    assert settings.provider == "custom"
    assert settings.model == "old"
    assert settings.base_url == "https://ai.example/v1"
    assert settings.keys["custom"] == "ai-key"
    assert project_repo.get_meta("schema_version") == "2"


def test_ai_dict_without_credentials_does_not_override_defaults(tmp_path):
    db_path = tmp_path / "test.db"
    project_repo = ProjectRepository(db_path=db_path)
    settings_repo = SettingsRepository(db_path=db_path)
    project_repo.add_project(
        ProjectConfig(name="P", ai={"selected_trackers": ["redmine"]})
    )

    migrate_projects_to_v2(project_repo, settings_repo, log=lambda message: None)

    settings = settings_repo.get_ai_settings()
    assert settings.provider == "opencode_go"
    assert settings.model == "deepseek-v4.1-flash"
    assert settings.keys == {}


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    project_repo = ProjectRepository(db_path=db_path)
    settings_repo = SettingsRepository(db_path=db_path)
    project_repo.add_project(ProjectConfig(name="P"))

    assert migrate_projects_to_v2(project_repo, settings_repo, log=print) == 1
    assert migrate_projects_to_v2(project_repo, settings_repo, log=print) == 0
    assert len(project_repo.list_users(project_repo.list_projects()[0].db_id)) == 1
