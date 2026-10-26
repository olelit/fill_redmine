import importlib.util
import os
from collections.abc import Callable
from pathlib import Path

from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository

DEFAULT_USER_LIST_PATH = Path(__file__).resolve().parent.parent / "user_list.py"
USERS_MIGRATED_KEY = "legacy_users_migrated"


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
