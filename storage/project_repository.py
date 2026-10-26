import json
import sqlite3
from pathlib import Path

from configs.project_config import ProjectConfig
from storage.database import create_schema, get_connection

COLUMNS = (
    "name, git_repo_path, git_author_email, workday_hours, "
    "exclude_dates, trackers_json, ai_json"
)


class ProjectRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = get_connection(db_path)
        create_schema(self.conn)

    def list_projects(self) -> list[ProjectConfig]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [self._row_to_project(row) for row in rows]

    def get_project(self, db_id: int) -> ProjectConfig | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (db_id,)
        ).fetchone()
        return self._row_to_project(row) if row is not None else None

    def find_by_name(self, name: str) -> ProjectConfig | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_project(row) if row is not None else None

    def add_project(self, project: ProjectConfig) -> int:
        cursor = self.conn.execute(
            f"INSERT INTO projects ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
            self._project_values(project),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_projects(self, projects: list[ProjectConfig]) -> None:
        with self.conn:
            self.conn.executemany(
                f"INSERT INTO projects ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [self._project_values(project) for project in projects],
            )

    def update_project(self, db_id: int, project: ProjectConfig) -> None:
        if self.get_project(db_id) is None:
            raise ValueError(f"Project {db_id} not found")
        self.conn.execute(
            """UPDATE projects SET
               name = ?, git_repo_path = ?, git_author_email = ?,
               workday_hours = ?, exclude_dates = ?, trackers_json = ?,
               ai_json = ?
               WHERE id = ?""",
            (*self._project_values(project), db_id),
        )
        self.conn.commit()

    def delete_project(self, db_id: int) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (db_id,))
        self.conn.commit()

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            """INSERT INTO app_meta (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        self.conn.commit()

    @staticmethod
    def _project_values(project: ProjectConfig) -> tuple:
        return (
            project.name,
            project.git_repo_path,
            project.git_author_email,
            project.workday_hours,
            json.dumps(project.exclude_dates, ensure_ascii=False),
            json.dumps(project.trackers, ensure_ascii=False),
            json.dumps(project.ai, ensure_ascii=False),
        )

    @staticmethod
    def _load_json(value: str, fallback):
        try:
            parsed = json.loads(value or "")
        except (json.JSONDecodeError, TypeError):
            return fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback

    @classmethod
    def _row_to_project(cls, row: sqlite3.Row) -> ProjectConfig:
        return ProjectConfig(
            name=row["name"],
            git_repo_path=row["git_repo_path"],
            git_author_email=row["git_author_email"],
            workday_hours=float(row["workday_hours"]),
            exclude_dates=cls._load_json(row["exclude_dates"], []),
            trackers=cls._load_json(row["trackers_json"], {}),
            ai=cls._load_json(row["ai_json"], {}),
            db_id=row["id"],
        )
