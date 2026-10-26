import os
import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    is_enable INTEGER NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    redmine_api_key TEXT NOT NULL DEFAULT '',
    user_id INTEGER NOT NULL,
    activity_id INTEGER NOT NULL,
    comment TEXT NOT NULL DEFAULT '',
    issue_id INTEGER NOT NULL,
    driver TEXT NOT NULL CHECK (driver IN ('manual', 'youtrack')),
    youtrack_access_token TEXT NOT NULL DEFAULT '',
    exclude_dates TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    git_repo_path TEXT NOT NULL DEFAULT '',
    git_author_email TEXT NOT NULL DEFAULT '',
    workday_hours REAL NOT NULL DEFAULT 8,
    exclude_dates TEXT NOT NULL DEFAULT '[]',
    trackers_json TEXT NOT NULL DEFAULT '{}',
    ai_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def get_default_db_path() -> Path:
    env_path = os.getenv("WORK_ASSISTANT_DB") or os.getenv("FILL_REDMINE_DB")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parent.parent / "work_assistant.db"


def get_legacy_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "fill_redmine.db"


def migrate_legacy_database(
    target_path: Path,
    legacy_path: Path,
    log: Callable[[str], None] = print,
) -> bool:
    if target_path.exists() or not legacy_path.exists():
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        legacy_path.rename(target_path)
        log(f"База данных перенесена: {legacy_path.name} → {target_path.name}")
    except OSError:
        shutil.copy2(legacy_path, target_path)
        log(f"База данных скопирована: {legacy_path.name} → {target_path.name}")

    try:
        os.chmod(target_path, 0o600)
    except OSError:
        pass
    return True


def migrate_default_legacy_database(log: Callable[[str], None] = print) -> bool:
    if os.getenv("WORK_ASSISTANT_DB") or os.getenv("FILL_REDMINE_DB"):
        return False
    return migrate_legacy_database(get_default_db_path(), get_legacy_db_path(), log=log)


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_default_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if db_path is None:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
