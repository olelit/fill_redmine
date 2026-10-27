import importlib.util
import os
from collections.abc import Callable
from pathlib import Path

from configs.ai_settings import AiSettings
from configs.project_config import ProjectConfig, ProjectUserConfig
from storage.project_repository import ProjectRepository
from storage.settings_repository import KEY as AI_SETTINGS_KEY, SettingsRepository
from storage.user_repository import UserRepository

DEFAULT_USER_LIST_PATH = Path(__file__).resolve().parent.parent / "user_list.py"
USERS_MIGRATED_KEY = "legacy_users_migrated"
SCHEMA_VERSION_KEY = "schema_version"


def migrate_from_user_list(
    repo: UserRepository,
    user_list_path: Path | None = None,
    log: Callable[[str], None] = print,
) -> bool:
    if repo.list_users():
        return False

    path = Path(user_list_path) if user_list_path is not None else DEFAULT_USER_LIST_PATH
    if not path.exists():
        return False

    try:
        spec = importlib.util.spec_from_file_location("_fill_redmine_user_list_migration", path)
        if spec is None or spec.loader is None:
            return False
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        users = getattr(module, "USERS", [])
        if not users:
            return False
        repo.add_users(users)
        migrated_path = path.with_name(path.name + ".migrated")
        path.rename(migrated_path)
        try:
            os.chmod(migrated_path, 0o600)
        except OSError:
            pass
        log(f"Перенесено юзеров: {len(users)}. Файл переименован в {migrated_path.name}")
        return True
    except Exception as exc:
        log(f"Предупреждение: миграция из {path.name} не удалась: {exc}")
        return False


def _unique_project_name(base: str, used: set[str]) -> str:
    candidate = base
    index = 2
    while candidate in used:
        candidate = f"{base} ({index})"
        index += 1
    used.add(candidate)
    return candidate


def migrate_users_to_projects(
    project_repo: ProjectRepository,
    user_repo: UserRepository,
    log: Callable[[str], None] = print,
) -> int:
    if project_repo.get_meta(USERS_MIGRATED_KEY) == "1":
        return 0

    users = user_repo.list_users()
    if not users:
        return 0

    used_names = {project.name for project in project_repo.list_projects()}
    projects: list[ProjectConfig] = []
    for user in users:
        trackers = {
            "redmine": {
                "api_key": user.redmine_api_key,
                "user_id": user.user_id,
                "activity_id": user.activity_id,
                "issue_id": user.issue_id,
                "comment": user.comment,
            }
        }
        if user.youtrack_access_token:
            trackers["youtrack"] = {
                "access_token": user.youtrack_access_token
            }
        projects.append(
            ProjectConfig(
                name=_unique_project_name(user.name, used_names),
                exclude_dates=list(user.exclude_dates),
                trackers=trackers,
            )
        )

    try:
        project_repo.add_projects(projects)
        project_repo.set_meta(USERS_MIGRATED_KEY, "1")
    except Exception as exc:
        log(f"Предупреждение: миграция юзеров в проекты не удалась: {exc}")
        return 0

    log(f"Юзеры перенесены в проекты: {len(projects)}")
    return len(projects)


def migrate_projects_to_v2(
    project_repo: ProjectRepository,
    settings_repo: SettingsRepository,
    log: Callable[[str], None] = print,
) -> int:
    if project_repo.get_meta(SCHEMA_VERSION_KEY) == "2":
        return 0

    projects = project_repo.list_projects()
    migrated = 0
    for project in projects:
        if not project.users and project.db_id is not None:
            project_repo.add_user(
                project.db_id,
                ProjectUserConfig(
                    name=project.name,
                    git_email=project.git_author_email,
                    trackers=project.trackers,
                ),
            )
            migrated += 1

    if settings_repo.get_raw(AI_SETTINGS_KEY) is None:
        legacy = None
        for project in projects:
            api_key = str(project.ai.get("api_key") or "").strip()
            model = str(project.ai.get("model") or "").strip()
            if model and api_key:
                legacy = project.ai
                break
        if legacy is not None:
            api_key = str(legacy.get("api_key") or "").strip()
            model = str(legacy.get("model") or "").strip()
            base_url = str(legacy.get("base_url") or "").strip()
            if base_url:
                provider = "custom"
            else:
                provider = "openai"
            settings_repo.save_ai_settings(
                AiSettings(
                    provider=provider,
                    model=model,
                    base_url=base_url,
                    keys={provider: api_key},
                )
            )

    project_repo.set_meta(SCHEMA_VERSION_KEY, "2")
    log(f"Миграция схемы v2: юзеров создано {migrated}")
    return migrated

