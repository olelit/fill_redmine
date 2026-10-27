import json
import sqlite3
from pathlib import Path

from configs.project_config import ProjectConfig, ProjectUserConfig
from storage.database import create_schema, get_connection

PROJECT_COLUMNS = (
    "name, git_repo_path, git_author_email, workday_hours, "
    "exclude_dates, default_comment, trackers_json, ai_json"
)
USER_COLUMNS = "project_id, name, git_email, trackers_json"


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
        with self.conn:
            cursor = self.conn.execute(
                f"INSERT INTO projects ({PROJECT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._project_values(project),
            )
            project_id = int(cursor.lastrowid)
            self._insert_users(project_id, project.users)
        return project_id

    def add_projects(self, projects: list[ProjectConfig]) -> None:
        with self.conn:
            self.conn.executemany(
                f"INSERT INTO projects ({PROJECT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [self._project_values(project) for project in projects],
            )

    def update_project(self, db_id: int, project: ProjectConfig) -> None:
        if self.get_project(db_id) is None:
            raise ValueError(f"Project {db_id} not found")
        self.conn.execute(
            """UPDATE projects SET
               name = ?, git_repo_path = ?, git_author_email = ?,
               workday_hours = ?, exclude_dates = ?, default_comment = ?,
               trackers_json = ?, ai_json = ?
               WHERE id = ?""",
            (*self._project_values(project), db_id),
        )
        self.conn.commit()

    def delete_project(self, db_id: int) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (db_id,))
        self.conn.commit()

    def list_users(self, project_id: int) -> list[ProjectUserConfig]:
        rows = self.conn.execute(
            "SELECT * FROM project_users WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def add_user(self, project_id: int, user: ProjectUserConfig) -> int:
        cursor = self.conn.execute(
            f"INSERT INTO project_users ({USER_COLUMNS}) VALUES (?, ?, ?, ?)",
            self._user_values(project_id, user),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def update_user(self, user_id: int, user: ProjectUserConfig) -> None:
        row = self.conn.execute(
            "SELECT project_id FROM project_users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"User {user_id} not found")
        self.conn.execute(
            """UPDATE project_users SET
               project_id = ?, name = ?, git_email = ?, trackers_json = ?
               WHERE id = ?""",
            (*self._user_values(int(row["project_id"]), user), user_id),
        )
        self.conn.commit()

    def delete_user(self, user_id: int) -> None:
        self.conn.execute("DELETE FROM project_users WHERE id = ?", (user_id,))
        self.conn.commit()

    def replace_users(self, project_id: int, users: list[ProjectUserConfig]) -> None:
        with self.conn:
            self.conn.execute(
                "DELETE FROM project_users WHERE project_id = ?", (project_id,)
            )
            self._insert_users(project_id, users)

    def merge_users_from(self, project_id: int, donor: ProjectConfig) -> int:
        current = self.get_project(project_id)
        if current is None:
            raise ValueError(f"Project {project_id} not found")

        self.conn.execute(
            """UPDATE projects SET
               git_repo_path = ?, workday_hours = ?, exclude_dates = ?,
               default_comment = ?
               WHERE id = ?""",
            (
                donor.git_repo_path,
                donor.workday_hours,
                json.dumps(donor.exclude_dates, ensure_ascii=False),
                donor.default_comment,
                project_id,
            ),
        )

        changed = 0
        existing = {user.name: user for user in self.list_users(project_id)}
        for donor_user in donor.users:
            current_user = existing.get(donor_user.name)
            if current_user is None:
                self.conn.execute(
                    f"INSERT INTO project_users ({USER_COLUMNS}) VALUES (?, ?, ?, ?)",
                    self._user_values(project_id, donor_user),
                )
                changed += 1
            else:
                self.conn.execute(
                    """UPDATE project_users SET
                       git_email = ?, trackers_json = ?
                       WHERE id = ?""",
                    (
                        donor_user.git_email,
                        json.dumps(donor_user.trackers, ensure_ascii=False),
                        current_user.db_id,
                    ),
                )
                changed += 1
        self.conn.commit()
        return changed

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

    def _insert_users(self, project_id: int, users: list[ProjectUserConfig]) -> None:
        self.conn.executemany(
            f"INSERT INTO project_users ({USER_COLUMNS}) VALUES (?, ?, ?, ?)",
            [self._user_values(project_id, user) for user in users],
        )

    @staticmethod
    def _project_values(project: ProjectConfig) -> tuple:
        return (
            project.name,
            project.git_repo_path,
            project.git_author_email,
            project.workday_hours,
            json.dumps(project.exclude_dates, ensure_ascii=False),
            project.default_comment,
            json.dumps(project.trackers, ensure_ascii=False),
            json.dumps(project.ai, ensure_ascii=False),
        )

    @staticmethod
    def _user_values(project_id: int, user: ProjectUserConfig) -> tuple:
        return (
            project_id,
            user.name,
            user.git_email,
            json.dumps(user.trackers, ensure_ascii=False),
        )

    @staticmethod
    def _load_json(value: str, fallback):
        try:
            parsed = json.loads(value or "")
        except (json.JSONDecodeError, TypeError):
            return fallback
        return parsed if isinstance(parsed, type(fallback)) else fallback

    def _row_to_project(self, row: sqlite3.Row) -> ProjectConfig:
        project = ProjectConfig(
            name=row["name"],
            git_repo_path=row["git_repo_path"],
            git_author_email=row["git_author_email"],
            workday_hours=float(row["workday_hours"]),
            exclude_dates=self._load_json(row["exclude_dates"], []),
            default_comment=row["default_comment"],
            trackers=self._load_json(row["trackers_json"], {}),
            ai=self._load_json(row["ai_json"], {}),
            db_id=row["id"],
        )
        project.users = self.list_users(row["id"])
        return project

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> ProjectUserConfig:
        return ProjectUserConfig(
            name=row["name"],
            git_email=row["git_email"],
            trackers=ProjectRepository._load_json(row["trackers_json"], {}),
            project_id=row["project_id"],
            db_id=row["id"],
        )
