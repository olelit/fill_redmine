import os
import sqlite3
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
"""


def get_default_db_path() -> Path:
    env_path = os.getenv("FILL_REDMINE_DB")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parent.parent / "fill_redmine.db"


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
