import importlib.util
from pathlib import Path
from typing import Callable

from storage.user_repository import UserRepository

DEFAULT_USER_LIST_PATH = Path(__file__).resolve().parent.parent / "user_list.py"


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
        for user in users:
            repo.add_user(user)
        migrated_path = path.with_name(path.name + ".migrated")
        path.rename(migrated_path)
        log(f"Перенесено юзеров: {len(users)}. Файл переименован в {migrated_path.name}")
        return True
    except Exception as exc:
        log(f"Предупреждение: миграция из {path.name} не удалась: {exc}")
        return False
