import json
import sqlite3
from pathlib import Path

from configs.user_config import UserConfig
from storage.database import create_schema, get_connection

COLUMNS = (
    "is_enable, name, redmine_api_key, user_id, activity_id, "
    "comment, issue_id, driver, youtrack_access_token, exclude_dates"
)


class UserRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = get_connection(db_path)
        create_schema(self.conn)

    def list_users(self) -> list[UserConfig]:
        rows = self.conn.execute("SELECT * FROM users ORDER BY id").fetchall()
        return [self._row_to_user(row) for row in rows]

    def get_user(self, db_id: int) -> UserConfig | None:
        row = self.conn.execute("SELECT * FROM users WHERE id = ?", (db_id,)).fetchone()
        return self._row_to_user(row) if row is not None else None

    def add_user(self, user: UserConfig) -> int:
        cursor = self.conn.execute(
            f"INSERT INTO users ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            self._user_values(user),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def add_users(self, users: list[UserConfig]) -> None:
        with self.conn:
            self.conn.executemany(
                f"INSERT INTO users ({COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [self._user_values(user) for user in users],
            )

    def update_user(self, db_id: int, user: UserConfig) -> None:
        if self.get_user(db_id) is None:
            raise ValueError(f"User {db_id} not found")
        self.conn.execute(
            """UPDATE users SET
               is_enable = ?, name = ?, redmine_api_key = ?, user_id = ?,
               activity_id = ?, comment = ?, issue_id = ?, driver = ?,
               youtrack_access_token = ?, exclude_dates = ?
               WHERE id = ?""",
            (*self._user_values(user), db_id),
        )
        self.conn.commit()

    def delete_user(self, db_id: int) -> None:
        self.conn.execute("DELETE FROM users WHERE id = ?", (db_id,))
        self.conn.commit()

    def set_enabled(self, db_id: int, enabled: bool) -> None:
        self.conn.execute(
            "UPDATE users SET is_enable = ? WHERE id = ?",
            (int(enabled), db_id),
        )
        self.conn.commit()

    @staticmethod
    def _user_values(user: UserConfig) -> tuple:
        return (
            int(user.is_enable),
            user.name,
            user.redmine_api_key,
            user.user_id,
            user.activity_id,
            user.comment,
            user.issue_id,
            user.driver,
            user.youtrack_access_token,
            json.dumps(user.exclude_dates),
        )

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> UserConfig:
        return UserConfig(
            is_enable=bool(row["is_enable"]),
            name=row["name"],
            redmine_api_key=row["redmine_api_key"],
            user_id=row["user_id"],
            activity_id=row["activity_id"],
            comment=row["comment"],
            issue_id=row["issue_id"],
            driver=row["driver"],
            youtrack_access_token=row["youtrack_access_token"],
            exclude_dates=json.loads(row["exclude_dates"] or "[]"),
            db_id=row["id"],
        )
