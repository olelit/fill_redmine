# Work Assistant Tracking v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переделать Work Assistant в проект-centric трекинг времени: несколько юзеров в проекте, трекер-назначение, источники (автозаполнение / другой трекер / коммиты), редактируемый отчёт и запись в Redmine/YouTrack. Глобальные AI-настройки: OpenCode Go, OpenAI, Anthropic, Custom.

**Architecture:** Проект хранит общие настройки, `project_users` — людей с JSON-конфигами трекеров. Новый `TrackingService` строит отчёт по дням, а `write_report` пишет включённые строки в выбранный трекер. AI-провайдеры вынесены в `clients/ai/` с адаптерами OpenAI Chat, OpenAI Responses и Anthropic Messages. GUI заменяется на главный экран со списком проектов, экран проекта с меню «Трекинг времени» и экран трекинга с панелью настроек и отчётом.

**Tech Stack:** Python 3.10+, Tkinter/ttk, SQLite, requests, pytest.

## Global Constraints

- Новые зависимости не добавлять.
- Все новые публичные функции и методы — с type hints.
- Импорты абсолютные, порядок: stdlib → third-party → локальные.
- Пользовательские строки GUI — на русском; технические поля — как в коде.
- Секреты в UI маскировать, в SQLite — открытый текст, файл БД `600`.
- В трекер-источник ничего не записывать; запись только в выбранное назначение.
- Комментарий по умолчанию — `development`; для коммитов — комментарий ИИ.
- CLI удаляется, остаётся только GUI.
- Старые таблицы и legacy-модули миграции сохраняются.
- Каждая задача заканчивается зелёными тестами и отдельным коммитом.

---

### Task 1: Project users storage

**Files:**
- Modify: `configs/project_config.py`
- Modify: `storage/database.py`
- Modify: `storage/project_repository.py`
- Modify: `tests/test_project_repository.py`

**Interfaces:**
- Consumes: existing `ProjectConfig`, `ProjectRepository`.
- Produces:
  - `ProjectUserConfig(name, git_email="", trackers={}, project_id=None, db_id=None)`
  - `ProjectConfig.default_comment`, `ProjectConfig.users`
  - `ProjectRepository.list_users(project_id)`, `add_user`, `update_user`, `delete_user`, `replace_users`, `merge_users_from`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_project_repository.py`:

```python
from configs.project_config import ProjectConfig, ProjectUserConfig


def make_user(name="Олег", **overrides) -> ProjectUserConfig:
    data = dict(
        name=name,
        git_email=f"{name.lower()}@example.com",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
            },
            "youtrack": {"access_token": "token", "issue_id": "PROJ-1"},
        },
    )
    data.update(overrides)
    return ProjectUserConfig(**data)


def test_project_users_roundtrip(repo):
    db_id = repo.add_project(make_project(users=[make_user()]))

    project = repo.get_project(db_id)

    assert project.default_comment == "development"
    assert len(project.users) == 1
    assert project.users[0].name == "Олег"
    assert project.users[0].trackers["youtrack"]["issue_id"] == "PROJ-1"


def test_add_update_delete_user(repo):
    project_id = repo.add_project(make_project())
    user_id = repo.add_user(project_id, make_user("Первый"))

    repo.update_user(user_id, make_user("Второй", git_email="new@example.com"))
    assert repo.list_users(project_id)[0].name == "Второй"
    assert repo.list_users(project_id)[0].git_email == "new@example.com"

    repo.delete_user(user_id)
    assert repo.list_users(project_id) == []


def test_replace_users_replaces_all(repo):
    project_id = repo.add_project(make_project(users=[make_user("Старый")]))

    repo.replace_users(project_id, [make_user("Новый")])

    assert [user.name for user in repo.list_users(project_id)] == ["Новый"]


def test_merge_users_from_updates_and_adds(repo):
    target_id = repo.add_project(make_project(name="Target", users=[make_user("Олег")]))
    donor = make_project(
        name="Donor",
        git_repo_path="/donor/repo",
        workday_hours=7.5,
        default_comment="donor",
        users=[
            make_user("Олег", git_email="updated@example.com"),
            make_user("Новый"),
        ],
    )
    donor_id = repo.add_project(donor)
    donor = repo.get_project(donor_id)

    repo.merge_users_from(target_id, donor)

    target = repo.get_project(target_id)
    assert target.git_repo_path == "/donor/repo"
    assert target.workday_hours == 7.5
    assert target.default_comment == "donor"
    assert [user.name for user in target.users] == ["Олег", "Новый"]
    assert target.users[0].git_email == "updated@example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_project_repository.py -q`
Expected: FAIL (unknown fields/methods).

- [ ] **Step 3: Update ProjectConfig**

```python
# configs/project_config.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectUserConfig:
    name: str
    git_email: str = ""
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)
    project_id: int | None = None
    db_id: int | None = None


@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    git_author_email: str = ""  # legacy
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    default_comment: str = "development"
    users: list[ProjectUserConfig] = field(default_factory=list)
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)  # legacy
    ai: dict[str, Any] = field(default_factory=dict)  # legacy
    db_id: int | None = None

    def tracker(self, kind: str) -> dict[str, Any]:
        return self.trackers.get(kind, {})

    def user_by_id(self, db_id: int) -> ProjectUserConfig | None:
        for user in self.users:
            if user.db_id == db_id:
                return user
        return None
```

- [ ] **Step 4: Extend schema**

Update `storage/database.py`:

```python
SCHEMA = """
-- users (legacy) остаётся как есть
CREATE TABLE IF NOT EXISTS users (...);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    git_repo_path TEXT NOT NULL DEFAULT '',
    git_author_email TEXT NOT NULL DEFAULT '',
    workday_hours REAL NOT NULL DEFAULT 8,
    exclude_dates TEXT NOT NULL DEFAULT '[]',
    trackers_json TEXT NOT NULL DEFAULT '{}',
    ai_json TEXT NOT NULL DEFAULT '{}',
    default_comment TEXT NOT NULL DEFAULT 'development'
);

CREATE TABLE IF NOT EXISTS project_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    git_email TEXT NOT NULL DEFAULT '',
    trackers_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, name)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _ensure_project_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(projects)")
    }
    if "default_comment" not in columns:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN default_comment TEXT NOT NULL DEFAULT 'development'"
        )


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _ensure_project_columns(conn)
    conn.commit()
```

- [ ] **Step 5: Rewrite ProjectRepository**

Replace `storage/project_repository.py` with:

```python
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
```

- [ ] **Step 6: Run tests and full suite**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_project_repository.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS (легаси-поля сохранены, старые тесты работают).

- [ ] **Step 7: Commit**

```bash
git add configs/project_config.py storage/database.py storage/project_repository.py tests/test_project_repository.py
git commit -m "feat: add project users storage"
```

---

### Task 2: AI settings storage and migration v2

**Files:**
- Create: `configs/ai_settings.py`
- Create: `storage/settings_repository.py`
- Modify: `storage/migration.py`
- Create: `tests/test_settings_repository.py`
- Create: `tests/test_migration_v2.py`

**Interfaces:**
- Consumes: `ProjectRepository`, `ProjectConfig`, legacy fields.
- Produces:
  - `AiSettings(provider="opencode_go", model="deepseek-v4.1-flash", base_url="", keys={})`
  - `SettingsRepository.get_ai_settings()`, `save_ai_settings(settings)`
  - `migrate_projects_to_v2(project_repo, settings_repo, log=print) -> int`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings_repository.py
from configs.ai_settings import AiSettings
from storage.settings_repository import SettingsRepository


def test_defaults(tmp_path):
    repo = SettingsRepository(db_path=tmp_path / "test.db")

    settings = repo.get_ai_settings()

    assert settings.provider == "opencode_go"
    assert settings.model == "deepseek-v4.1-flash"
    assert settings.keys == {}


def test_roundtrip(tmp_path):
    repo = SettingsRepository(db_path=tmp_path / "test.db")
    settings = AiSettings(
        provider="openai",
        model="gpt-6",
        keys={"openai": "secret"},
    )

    repo.save_ai_settings(settings)

    assert repo.get_ai_settings() == settings
```

```python
# tests/test_migration_v2.py
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


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "test.db"
    project_repo = ProjectRepository(db_path=db_path)
    settings_repo = SettingsRepository(db_path=db_path)
    project_repo.add_project(ProjectConfig(name="P"))

    assert migrate_projects_to_v2(project_repo, settings_repo, log=print) == 1
    assert migrate_projects_to_v2(project_repo, settings_repo, log=print) == 0
    assert len(project_repo.list_users(project_repo.list_projects()[0].db_id)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_settings_repository.py tests/test_migration_v2.py -q`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement AiSettings and SettingsRepository**

```python
# configs/ai_settings.py
from dataclasses import dataclass, field


@dataclass
class AiSettings:
    provider: str = "opencode_go"
    model: str = "deepseek-v4.1-flash"
    base_url: str = ""
    keys: dict[str, str] = field(default_factory=dict)

    def key_for(self, provider: str) -> str:
        return self.keys.get(provider, "")
```

```python
# storage/settings_repository.py
import json
from pathlib import Path

from configs.ai_settings import AiSettings
from storage.database import create_schema, get_connection

KEY = "ai_settings"


class SettingsRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.conn = get_connection(db_path)
        create_schema(self.conn)

    def get_ai_settings(self) -> AiSettings:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (KEY,)
        ).fetchone()
        if row is None:
            return AiSettings()
        try:
            data = json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return AiSettings()
        keys = data.get("keys")
        if not isinstance(keys, dict):
            keys = {}
        return AiSettings(
            provider=str(data.get("provider") or "opencode_go"),
            model=str(data.get("model") or "deepseek-v4.1-flash"),
            base_url=str(data.get("base_url") or ""),
            keys={str(k): str(v) for k, v in keys.items()},
        )

    def save_ai_settings(self, settings: AiSettings) -> None:
        payload = json.dumps(
            {
                "provider": settings.provider,
                "model": settings.model,
                "base_url": settings.base_url,
                "keys": settings.keys,
            },
            ensure_ascii=False,
        )
        self.conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (KEY, payload),
        )
        self.conn.commit()

    def get_raw(self, key: str) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else None

    def set_raw(self, key: str, value: str) -> None:
        self.conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
            (key, value),
        )
        self.conn.commit()
```

- [ ] **Step 4: Implement migration v2**

Append to `storage/migration.py`:

```python
from configs.ai_settings import AiSettings
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository

SCHEMA_VERSION_KEY = "schema_version"


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
        if not project.users:
            project_repo.add_user(
                project.db_id,
                ProjectUserConfig(
                    name=project.name,
                    git_email=project.git_author_email,
                    trackers=project.trackers,
                ),
            )
            migrated += 1

    if settings_repo.get_raw("ai_settings") is None:
        legacy = next((p.ai for p in projects if p.ai), None)
        if legacy:
            settings_repo.save_ai_settings(
                AiSettings(
                    provider="custom",
                    model=str(legacy.get("model", "")),
                    base_url=str(legacy.get("base_url", "")),
                    keys={"custom": str(legacy.get("api_key", ""))},
                )
            )

    project_repo.set_meta(SCHEMA_VERSION_KEY, "2")
    log(f"Миграция схемы v2: юзеров создано {migrated}")
    return migrated
```

Не забудьте импортировать `ProjectUserConfig` в `storage/migration.py`.

- [ ] **Step 5: Run tests and full suite**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_settings_repository.py tests/test_migration_v2.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add configs/ai_settings.py storage/settings_repository.py storage/migration.py tests/test_settings_repository.py tests/test_migration_v2.py
git commit -m "feat: add AI settings and schema v2 migration"
```

---

### Task 3: Tracker write support

**Files:**
- Modify: `clients/redmine_client.py`
- Modify: `trackers/redmine.py`
- Modify: `clients/youtrack_client.py`
- Modify: `trackers/youtrack.py`
- Modify: `tests/test_redmine_tracker.py`
- Modify: `tests/test_youtrack_tracker.py`

**Interfaces:**
- Consumes: `WorklogDTO`.
- Produces:
  - `RedmineClient.create_time_entries_sync(user_id, issue_id, activity_id, records) -> list[tuple[str,str]]`
  - `RedmineTracker.create_worklogs(records) -> list[tuple[str,str]]`
  - `YoutrackClient.create_work_items(issue_id, records) -> list[tuple[str,str]]`
  - `YoutrackTracker.create_worklogs(records) -> list[tuple[str,str]]`
  - `YoutrackTracker` field `issue_id: str`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_redmine_tracker.py`:

```python
def test_create_worklogs_posts_time_entries():
    tracker = RedmineTracker(
        {"api_key": "key", "user_id": 16, "activity_id": 9, "issue_id": 2682}
    )
    response = MagicMock()
    response.status_code = 201
    response.text = ""

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.requests.post",
        return_value=response,
    ) as mock_post:
        errors = tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )

    assert errors == []
    body = mock_post.call_args.kwargs["json"]
    assert body["time_entry"]["issue_id"] == 2682
    assert body["time_entry"]["user_id"] == 16
    assert body["time_entry"]["hours"] == 4
    assert body["time_entry"]["comments"] == "dev"


def test_create_worklogs_reports_http_error():
    tracker = RedmineTracker(
        {"api_key": "key", "user_id": 16, "activity_id": 9, "issue_id": 2682}
    )
    response = MagicMock()
    response.status_code = 422
    response.text = "bad"

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch("clients.redmine_client.requests.post", return_value=response):
        errors = tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )

    assert errors == [("2026-10-27", "422 bad")]
```

Append to `tests/test_youtrack_tracker.py`:

```python
def test_create_worklogs_posts_work_items():
    tracker = YoutrackTracker({"access_token": "token", "issue_id": "PROJ-1"})
    response = MagicMock()
    response.status_code = 200
    response.text = "{}"

    with patch(
        "clients.youtrack_client.Config.get_youtrack_base_url",
        return_value="http://youtrack",
    ), patch(
        "clients.youtrack_client.requests.post",
        return_value=response,
    ) as mock_post:
        errors = tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )

    assert errors == []
    body = mock_post.call_args.kwargs["json"]
    assert body["duration"]["minutes"] == 240
    assert body["text"] == "dev"
    assert "PROJ-1" in mock_post.call_args.args[0]


def test_create_worklogs_requires_issue_id():
    tracker = YoutrackTracker({"access_token": "token"})

    with pytest.raises(ValueError, match="issue_id"):
        tracker.create_worklogs(
            [WorklogDTO(date="2026-10-27", hours=4, description="dev")]
        )
```

- [ ] **Step 2: Implement Redmine write**

```python
    def create_time_entries_sync(
        self,
        user_id: int,
        issue_id: int,
        activity_id: int,
        records: list[WorklogDTO],
    ) -> list[tuple[str, str]]:
        url = f"{self.base_url}/time_entries.json"
        headers = {"X-Redmine-API-Key": self.api_key}
        errors: list[tuple[str, str]] = []
        for record in records:
            response = requests.post(
                url,
                headers=headers,
                json={
                    "time_entry": {
                        "issue_id": issue_id,
                        "user_id": user_id,
                        "spent_on": record.date,
                        "hours": record.hours,
                        "activity_id": activity_id,
                        "comments": record.description or "development",
                    }
                },
                timeout=10,
            )
            if not 200 <= response.status_code < 300:
                errors.append((record.date, f"{response.status_code} {response.text}"))
        return errors
```

В `trackers/redmine.py`:

```python
    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        client = RedmineClient(api_key=self.config["api_key"])
        return client.create_time_entries_sync(
            user_id=int(self.config["user_id"]),
            issue_id=int(self.config["issue_id"]),
            activity_id=int(self.config["activity_id"]),
            records=records,
        )
```

Удалите необязательное поле `comment` из `RedmineTracker.fields` (комментарий теперь проектный).

- [ ] **Step 3: Implement YouTrack write**

```python
    def create_work_items(
        self, issue_id: str, records: list[WorklogDTO]
    ) -> list[tuple[str, str]]:
        url = f"{self.base_url}/api/issues/{issue_id}/timeTracking/workItems"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        errors: list[tuple[str, str]] = []
        for record in records:
            day = date.fromisoformat(record.date)
            start_ms = int(
                datetime.combine(day, datetime.min.time()).timestamp() * 1000
            )
            response = requests.post(
                url,
                headers=headers,
                json={
                    "date": start_ms,
                    "duration": {"minutes": int(round(record.hours * 60))},
                    "text": record.description or "development",
                },
                timeout=10,
            )
            if not 200 <= response.status_code < 300:
                errors.append((record.date, f"{response.status_code} {response.text}"))
        return errors
```

В `trackers/youtrack.py`:

```python
    fields = (
        TrackerField("access_token", "Access token", kind="secret"),
        TrackerField("issue_id", "Issue ID"),
    )

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        issue_id = str(self.config.get("issue_id", "")).strip()
        if not issue_id:
            raise ValueError("YouTrack не настроен: issue_id")
        client = YoutrackClient(access_token=self.config["access_token"])
        return client.create_work_items(issue_id, records)
```

- [ ] **Step 4: Run tests and full suite**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_redmine_tracker.py tests/test_youtrack_tracker.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/redmine_client.py clients/youtrack_client.py trackers/redmine.py trackers/youtrack.py tests/test_redmine_tracker.py tests/test_youtrack_tracker.py
git commit -m "feat: add Redmine and YouTrack worklog writes"
```

---

### Task 4: AI provider layer

**Files:**
- Create: `clients/ai/__init__.py`
- Create: `clients/ai/base.py`
- Create: `clients/ai/openai_chat.py`
- Create: `clients/ai/anthropic_messages.py`
- Create: `clients/ai/openai_responses.py`
- Create: `clients/ai/opencode_go.py`
- Create: `clients/ai/factory.py`
- Create: `tests/test_ai_providers.py`

**Interfaces:**
- Consumes: `AiSettings`.
- Produces:
  - `AiError`
  - `AiClient` protocol with `complete_json`, `list_models`, `check_connection`
  - `create_ai_client(settings) -> AiClient`
  - `OpenCodeGoClient` routing.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_providers.py
from unittest.mock import MagicMock, patch

import pytest

from clients.ai.base import AiError, parse_json_object
from clients.ai.factory import create_ai_client
from clients.ai.opencode_go import ANTHROPIC_MODELS, RESPONSES_MODELS
from configs.ai_settings import AiSettings


def response(payload, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    result.text = str(payload)
    return result


def test_parse_json_object_with_fence():
    assert parse_json_object('```json\n{"summary": "ok"}\n```') == {"summary": "ok"}


def test_openai_chat_complete_json():
    settings = AiSettings(
        provider="openai", model="gpt", keys={"openai": "key"}
    )
    client = create_ai_client(settings)
    with patch(
        "clients.ai.openai_chat.requests.post",
        return_value=response(
            {"choices": [{"message": {"content": '{"summary": "ok"}'}}]}
        ),
    ) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    assert post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer key"


def test_anthropic_messages_complete_json():
    settings = AiSettings(
        provider="anthropic", model="claude", keys={"anthropic": "key"}
    )
    client = create_ai_client(settings)
    with patch(
        "clients.ai.anthropic_messages.requests.post",
        return_value=response(
            {"content": [{"type": "text", "text": '{"summary": "ok"}'}]}
        ),
    ) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
    assert post.call_args.kwargs["headers"]["x-api-key"] == "key"


def test_opencode_go_routes_anthropic_models():
    settings = AiSettings(
        provider="opencode_go",
        model=next(iter(ANTHROPIC_MODELS)),
        keys={"opencode_go": "key"},
    )
    client = create_ai_client(settings)

    assert client.base_url.endswith("/anthropic/v1")


def test_opencode_go_routes_responses_models():
    settings = AiSettings(
        provider="opencode_go",
        model=next(iter(RESPONSES_MODELS)),
        keys={"opencode_go": "key"},
    )
    client = create_ai_client(settings)

    assert client.base_url.endswith("/openai/v1")


def test_missing_key_raises():
    with pytest.raises(AiError, match="ключ"):
        create_ai_client(AiSettings(provider="openai", model="gpt"))
```

- [ ] **Step 2: Implement base and adapters**

```python
# clients/ai/base.py
import json
from typing import Protocol


class AiError(RuntimeError):
    pass


class AiClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict: ...
    def list_models(self) -> list[str]: ...
    def check_connection(self) -> None: ...


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        raise AiError("ИИ вернул ответ без JSON-объекта")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(f"ИИ вернул невалидный JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiError("ИИ вернул JSON не-объект")
    return parsed
```

```python
# clients/ai/openai_chat.py
from typing import Any

import requests

from clients.ai.base import AiError, parse_json_object


class OpenAIChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        if not isinstance(content, str):
            raise AiError("ИИ вернул пустой ответ")
        return parse_json_object(content)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json().get("data", [])
        return sorted(str(item["id"]) for item in data if "id" in item)

    def check_connection(self) -> None:
        self.list_models()
```

```python
# clients/ai/anthropic_messages.py
import requests

from clients.ai.base import AiError, parse_json_object


class AnthropicMessagesClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
        use_bearer: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}
        self.use_bearer = use_bearer

    def _headers(self) -> dict[str, str]:
        auth = (
            {"Authorization": f"Bearer {self.api_key}"}
            if self.use_bearer
            else {"x-api-key": self.api_key}
        )
        return {
            **auth,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/messages",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        try:
            parts = response.json()["content"]
            text = "".join(
                part.get("text", "")
                for part in parts
                if part.get("type") == "text"
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        return parse_json_object(text)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json().get("data", [])
        return sorted(str(item["id"]) for item in data if "id" in item)

    def check_connection(self) -> None:
        self.list_models()
```

```python
# clients/ai/openai_responses.py
import requests

from clients.ai.base import AiError, parse_json_object


class OpenAIResponsesClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        try:
            response = requests.post(
                f"{self.base_url}/responses",
                headers=self._headers(),
                json={
                    "model": self.model,
                    "instructions": system_prompt,
                    "input": user_prompt,
                },
                timeout=120,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        text = payload.get("output_text")
        if not text:
            parts: list[str] = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
            text = "".join(parts)
        if not text:
            raise AiError("ИИ вернул пустой ответ")
        return parse_json_object(text)

    def list_models(self) -> list[str]:
        try:
            response = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30,
            )
        except requests.RequestException as exc:
            raise AiError(f"Ошибка сети ИИ: {exc}") from exc
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json().get("data", [])
        return sorted(str(item["id"]) for item in data if "id" in item)

    def check_connection(self) -> None:
        self.list_models()
```

```python
# clients/ai/opencode_go.py
import uuid

from clients.ai.anthropic_messages import AnthropicMessagesClient
from clients.ai.base import AiError
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.openai_responses import OpenAIResponsesClient

BASE_URL = "https://opencode.ai/inference/go"
ANTHROPIC_MODELS = {
    "claude-haiku-5-5",
    "minimax-m3",
    "minimax-m2.7",
    "qwen3.8-max",
    "qwen3.8-flash",
    "qwen3.7-plus",
}
RESPONSES_MODELS = {
    "gpt-6-luna",
    "gpt-5.6-luna",
    "grok-4.7",
    "grok-4.6",
    "muse-spark-1.3-contributor",
    "muse-spark-1.2-contributor",
}
SESSION_ID = str(uuid.uuid4())


class OpenCodeGoClient:
    def __init__(self, model: str, api_key: str) -> None:
        if not api_key:
            raise AiError("Не задан API-ключ OpenCode Go")
        self.model = model
        self.api_key = api_key
        headers = {
            "User-Agent": "WorkAssistant/1.0",
            "x-opencode-session": SESSION_ID,
        }
        if model in ANTHROPIC_MODELS:
            self.base_url = f"{BASE_URL}/anthropic/v1"
            self._client = AnthropicMessagesClient(
                self.base_url,
                model,
                api_key,
                extra_headers=headers,
                use_bearer=False,
            )
        elif model in RESPONSES_MODELS:
            self.base_url = f"{BASE_URL}/openai/v1"
            self._client = OpenAIResponsesClient(
                self.base_url, model, api_key, extra_headers=headers
            )
        else:
            self.base_url = f"{BASE_URL}/openai/v1"
            self._client = OpenAIChatClient(
                self.base_url, model, api_key, extra_headers=headers
            )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return self._client.complete_json(system_prompt, user_prompt)

    def list_models(self) -> list[str]:
        import requests

        response = requests.get(
            f"{BASE_URL}/v1/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )
        if not 200 <= response.status_code < 300:
            raise AiError(f"HTTP {response.status_code}: {response.text[:500]}")
        data = response.json().get("data", [])
        return sorted(str(item["id"]) for item in data if "id" in item)

    def check_connection(self) -> None:
        self.list_models()
```

```python
# clients/ai/factory.py
from clients.ai.anthropic_messages import AnthropicMessagesClient
from clients.ai.base import AiClient, AiError
from clients.ai.openai_chat import OpenAIChatClient
from clients.ai.opencode_go import OpenCodeGoClient
from configs.ai_settings import AiSettings

PROVIDERS = ("opencode_go", "openai", "anthropic", "custom")


def create_ai_client(settings: AiSettings) -> AiClient:
    key = settings.key_for(settings.provider)
    if not settings.model:
        raise AiError("Не задана модель ИИ")
    if not key:
        raise AiError(f"Не задан API-ключ для {settings.provider}")
    if settings.provider == "opencode_go":
        return OpenCodeGoClient(settings.model, key)
    if settings.provider == "openai":
        return OpenAIChatClient("https://api.openai.com/v1", settings.model, key)
    if settings.provider == "anthropic":
        return AnthropicMessagesClient(
            "https://api.anthropic.com/v1", settings.model, key
        )
    if settings.provider == "custom":
        if not settings.base_url:
            raise AiError("Не задан base_url для custom-провайдера")
        return OpenAIChatClient(settings.base_url, settings.model, key)
    raise AiError(f"Неизвестный AI-провайдер: {settings.provider}")
```

```python
# clients/ai/__init__.py
from clients.ai.base import AiClient, AiError
from clients.ai.factory import create_ai_client

__all__ = ["AiClient", "AiError", "create_ai_client"]
```

- [ ] **Step 3: Run tests and full suite**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_ai_providers.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add clients/ai tests/test_ai_providers.py
git commit -m "feat: add multi-provider AI layer"
```

---

### Task 5: Tracking report — autofill and tracker source

**Files:**
- Create: `dto/tracking_dto.py`
- Create: `services/tracking_service.py`
- Create: `tests/test_tracking_service.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `ProjectUserConfig`, `BaseTracker`, `build_tracker`, `WorklogDTO`.
- Produces:
  - `TrackingSource`, `TrackingRow`, `TrackingReport`, `TrackingWriteResult`, `TrackingError`
  - `TrackingService.generate_report(...)` для `AUTOFILL` и `TRACKER`
  - `TrackingService.write_report(...)` (реализация в Task 6; в этой задаче можно заготовка `raise NotImplementedError`)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tracking_service.py
from datetime import date

import pytest

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import TrackingSource
from dto.worklog_dto import WorklogDTO
from services.tracking_service import TrackingError, TrackingService
from trackers.base import BaseTracker, TrackerField


class FakeTracker(BaseTracker):
    kind = "fake"
    label = "Fake"
    fields = (TrackerField("token", "Token"),)
    can_write = True

    def __init__(self, config, worklogs=None):
        super().__init__(config)
        self.worklogs = worklogs or []
        self.written = []

    def get_worklogs(self, start, end):
        return list(self.worklogs)

    def create_worklogs(self, records):
        self.written.extend(records)
        return []


def project_with_users(**overrides):
    data = dict(
        name="P",
        workday_hours=8,
        default_comment="development",
        users=[
            ProjectUserConfig(
                name="A",
                db_id=1,
                git_email="a@example.com",
                trackers={"fake": {"token": "t"}},
            ),
            ProjectUserConfig(
                name="B",
                db_id=2,
                git_email="b@example.com",
                trackers={"fake": {"token": "t"}},
            ),
        ],
    )
    data.update(overrides)
    return ProjectConfig(**data)


def test_autofill_fills_deficit_for_weekdays():
    tracker = FakeTracker(
        {"token": "t"},
        worklogs=[WorklogDTO(date="2026-10-01", hours=3)],
    )
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users()

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert [(r.date, r.existing_hours, r.proposed_hours) for r in report.rows] == [
        ("2026-10-01", 3, 5),
        ("2026-10-02", 0, 8),
    ]
    assert all(r.comment == "development" for r in report.rows)


def test_autofill_excludes_weekend_and_excluded_date():
    tracker = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users(exclude_dates=["2026-10-05"])

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 3),
        end=date(2026, 10, 5),
    )

    assert [r.proposed_hours for r in report.rows] == [0, 0, 0]


def test_tracker_source_copies_all_hours():
    destination = FakeTracker({"token": "t"})
    source = FakeTracker(
        {"token": "t"},
        worklogs=[
            WorklogDTO(date="2026-10-01", hours=4),
            WorklogDTO(date="2026-10-02", hours=6),
        ],
    )
    service = TrackingService(
        tracker_builder=lambda kind, config: source if kind == "source" else destination
    )
    project = project_with_users(
        users=[
            ProjectUserConfig(
                name="A",
                db_id=1,
                trackers={"fake": {"token": "t"}, "source": {"token": "t"}},
            )
        ]
    )

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.TRACKER,
        source_kind="source",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert [r.proposed_hours for r in report.rows] == [4, 6]
    assert all(r.include for r in report.rows)


def test_source_cannot_equal_destination():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))

    with pytest.raises(TrackingError, match="совпадать"):
        service.generate_report(
            project_with_users(),
            selected_user_ids=[1],
            destination_kind="fake",
            source=TrackingSource.TRACKER,
            source_kind="fake",
            start=date(2026, 10, 1),
            end=date(2026, 10, 2),
        )


def test_missing_destination_config_is_reported():
    service = TrackingService(tracker_builder=lambda kind, config: FakeTracker(config))
    project = project_with_users(
        users=[ProjectUserConfig(name="A", db_id=1, trackers={})]
    )

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 2),
    )

    assert report.rows == []
    assert any("A" in error for error in report.errors)
```

- [ ] **Step 2: Implement DTOs and service**

```python
# dto/tracking_dto.py
from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TrackingSource(str, Enum):
    AUTOFILL = "autofill"
    TRACKER = "tracker"
    COMMITS = "commits"


@dataclass
class TrackingRow:
    row_id: str
    user_id: int
    user_name: str
    date: str
    existing_hours: float
    proposed_hours: float
    comment: str
    source_details: str = ""
    include: bool = True
    status: str = ""
    error: str = ""


@dataclass
class TrackingReport:
    destination_kind: str
    source: TrackingSource
    source_kind: str = ""
    start: date | None = None
    end: date | None = None
    rows: list[TrackingRow] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TrackingWriteResult:
    written: int = 0
    errors: list[tuple[str, str, str]] = field(default_factory=list)
```

```python
# services/tracking_service.py
from collections.abc import Callable
from datetime import date, timedelta

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import (
    TrackingReport,
    TrackingRow,
    TrackingSource,
    TrackingWriteResult,
)
from dto.worklog_dto import WorklogDTO
from trackers.base import BaseTracker
from trackers.registry import build_tracker


class TrackingError(RuntimeError):
    pass


class TrackingService:
    def __init__(
        self,
        tracker_builder: Callable[[str, dict], BaseTracker | None] = build_tracker,
        log: Callable[[str], None] = print,
    ) -> None:
        self.tracker_builder = tracker_builder
        self.log = log

    def generate_report(
        self,
        project: ProjectConfig,
        selected_user_ids: list[int],
        destination_kind: str,
        source: TrackingSource,
        source_kind: str,
        start: date,
        end: date,
        ai_settings=None,
    ) -> TrackingReport:
        if start > end:
            raise TrackingError("Начало периода позже конца")
        users = [user for user in project.users if user.db_id in selected_user_ids]
        if not users:
            raise TrackingError("Не выбран ни один юзер")

        report = TrackingReport(
            destination_kind=destination_kind,
            source=source,
            source_kind=source_kind,
            start=start,
            end=end,
        )
        for user in users:
            try:
                self._add_user_rows(
                    report, project, user, destination_kind, source,
                    source_kind, start, end, ai_settings,
                )
            except Exception as exc:
                report.errors.append(f"{user.name}: {exc}")
        report.rows.sort(key=lambda row: (row.user_name, row.date))
        return report

    def _add_user_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        destination_kind: str,
        source: TrackingSource,
        source_kind: str,
        start: date,
        end: date,
        ai_settings,
    ) -> None:
        destination = self._tracker(user, destination_kind)
        existing = self._existing_by_day(destination, start, end)
        if source is TrackingSource.AUTOFILL:
            self._add_autofill_rows(report, project, user, existing, start, end)
            return
        if source is TrackingSource.TRACKER:
            if source_kind == destination_kind:
                raise TrackingError("Источник и назначение не могут совпадать")
            source_tracker = self._tracker(user, source_kind)
            source_by_day = self._existing_by_day(source_tracker, start, end)
            self._add_tracker_rows(report, project, user, existing, source_by_day, start, end)
            return
        raise TrackingError(f"Источник {source} пока не поддерживается")

    def _tracker(self, user: ProjectUserConfig, kind: str) -> BaseTracker:
        tracker = self.tracker_builder(kind, user.trackers.get(kind, {}))
        if tracker is None:
            raise TrackingError(f"неизвестный трекер {kind}")
        if not tracker.is_configured():
            raise TrackingError(f"трекер {tracker.label} не настроен")
        return tracker

    @staticmethod
    def _existing_by_day(
        tracker: BaseTracker, start: date, end: date
    ) -> dict[str, float]:
        result: dict[str, float] = {}
        for worklog in tracker.get_worklogs(start, end):
            result[worklog.date] = result.get(worklog.date, 0) + worklog.hours
        return result

    def _add_autofill_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        existing: dict[str, float],
        start: date,
        end: date,
    ) -> None:
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            proposed = max(0.0, round(target - existing_hours, 2))
            report.rows.append(
                TrackingRow(
                    row_id=f"{user.db_id}:{iso}",
                    user_id=int(user.db_id),
                    user_name=user.name,
                    date=iso,
                    existing_hours=existing_hours,
                    proposed_hours=proposed,
                    comment=project.default_comment,
                    include=proposed > 0,
                )
            )
            current += timedelta(days=1)

    def _add_tracker_rows(
        self,
        report: TrackingReport,
        project: ProjectConfig,
        user: ProjectUserConfig,
        existing: dict[str, float],
        source_by_day: dict[str, float],
        start: date,
        end: date,
    ) -> None:
        current = start
        while current <= end:
            iso = current.isoformat()
            proposed = round(source_by_day.get(iso, 0.0), 2)
            report.rows.append(
                TrackingRow(
                    row_id=f"{user.db_id}:{iso}",
                    user_id=int(user.db_id),
                    user_name=user.name,
                    date=iso,
                    existing_hours=round(existing.get(iso, 0.0), 2),
                    proposed_hours=proposed,
                    comment=project.default_comment,
                    source_details=report.source_kind,
                    include=proposed > 0,
                )
            )
            current += timedelta(days=1)

    def write_report(
        self, project: ProjectConfig, report: TrackingReport
    ) -> TrackingWriteResult:
        raise NotImplementedError
```

- [ ] **Step 3: Run tests and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_tracking_service.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

```bash
git add dto/tracking_dto.py services/tracking_service.py tests/test_tracking_service.py
git commit -m "feat: add tracking report for autofill and tracker sources"
```

---

### Task 6: Tracking — commits source, AI plan and write

**Files:**
- Create: `services/tracking_plan_service.py`
- Modify: `services/tracking_service.py`
- Modify: `tests/test_tracking_service.py`
- Create: `tests/test_tracking_write.py`

**Interfaces:**
- Consumes: `AiClient`, `GitClient`, `GitCommitDTO`, `CommitPlanDTO`, `DayPlanDTO`.
- Produces:
  - `TrackingPlanService.build_plan(project, user, destination, existing, start, end, commits, ai_client) -> CommitPlanDTO`
  - `TrackingService.generate_report` support `COMMITS`
  - `TrackingService.write_report` implementation.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tracking_service.py`:

```python
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from dto.git_commit_dto import GitCommitDTO


class FakeAi:
    def __init__(self, plan):
        self.plan = plan

    def complete_json(self, system_prompt, user_prompt):
        return self.plan


class FakeGit:
    def __init__(self, commits):
        self.commits = commits

    def list_commits(self, email, start, end):
        return list(self.commits)


def test_commits_source_uses_ai_plan(monkeypatch):
    destination = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: destination)
    service.git_client_factory = lambda path: FakeGit(
        [
            GitCommitDTO(
                hash="abc",
                author_name="A",
                author_email="a@example.com",
                date="2026-10-01T10:00:00+00:00",
                subject="Add feature",
            )
        ]
    )
    service.ai_client_factory = lambda settings: FakeAi(
        {
            "summary": "ok",
            "days": [
                {
                    "date": "2026-10-01",
                    "hours": 4,
                    "comment": "Сделал фичу",
                    "commit_hashes": ["abc"],
                    "confidence": "high",
                }
            ],
        }
    )
    project = project_with_users(git_repo_path="/repo")

    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.COMMITS,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
        ai_settings=object(),
    )

    assert report.rows[0].proposed_hours == 4
    assert report.rows[0].comment == "Сделал фичу"


def test_write_report_writes_only_included_rows():
    tracker = FakeTracker({"token": "t"})
    service = TrackingService(tracker_builder=lambda kind, config: tracker)
    project = project_with_users()
    report = service.generate_report(
        project,
        selected_user_ids=[1],
        destination_kind="fake",
        source=TrackingSource.AUTOFILL,
        source_kind="",
        start=date(2026, 10, 1),
        end=date(2026, 10, 1),
    )
    report.rows[0].proposed_hours = 5
    report.rows[0].comment = "dev"
    report.rows[0].include = True

    result = service.write_report(project, report)

    assert result.written == 1
    assert tracker.written[0].hours == 5
    assert report.rows[0].status == "записано"
    assert report.rows[0].include is False
```

- [ ] **Step 2: Implement tracking plan service**

```python
# services/tracking_plan_service.py
import json
from datetime import date, timedelta

from clients.ai.base import AiClient
from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from dto.git_commit_dto import GitCommitDTO

SYSTEM_PROMPT = """Ты — ассистент по учёту рабочего времени.
Верни ТОЛЬКО JSON-объект:
{"summary": "итог", "days": [{"date": "YYYY-MM-DD", "hours": 0.0,
"comment": "кратко", "commit_hashes": ["hash"], "confidence": "high|medium|low"}]}
Правила: используй только переданные коммиты и хеши; не придумывай работу без
коммитов; часы не больше deficit_hours и кратны 0.5; комментарии по-русски.
"""


class TrackingPlanService:
    def __init__(self, ai_client: AiClient, log=print) -> None:
        self.ai_client = ai_client
        self.log = log

    def build_plan(
        self,
        project: ProjectConfig,
        user: ProjectUserConfig,
        destination_kind: str,
        existing: dict[str, float],
        start: date,
        end: date,
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        days: list[DayPlanDTO] = []
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            days.append(
                DayPlanDTO(
                    date=iso,
                    existing_hours=existing_hours,
                    deficit_hours=max(0.0, round(target - existing_hours, 2)),
                    planned_hours=0.0,
                )
            )
            current += timedelta(days=1)

        payload = {
            "project": project.name,
            "user": user.name,
            "destination": destination_kind,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "days": [
                {
                    "date": day.date,
                    "existing_hours": day.existing_hours,
                    "deficit_hours": day.deficit_hours,
                    "commits": [
                        {"hash": c.hash, "subject": c.subject, "body": c.body[:300]}
                        for c in commits
                        if c.date[:10] == day.date
                    ],
                }
                for day in days
            ],
        }
        raw = self.ai_client.complete_json(
            SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2)
        )
        return self._apply(days, raw, commits)

    def _apply(self, days, raw, commits):
        by_date = {day.date: day for day in days}
        known = {commit.hash for commit in commits}
        for item in raw.get("days", []):
            if not isinstance(item, dict):
                continue
            day = by_date.get(str(item.get("date", "")))
            if day is None:
                continue
            try:
                hours = float(item.get("hours", 0))
            except (TypeError, ValueError):
                continue
            hours = round(hours * 2) / 2
            max_half = int(day.deficit_hours * 2) / 2
            day.planned_hours = max(0.0, min(hours, max_half))
            day.comment = str(item.get("comment", "")).strip()
            hashes = item.get("commit_hashes", [])
            day.commit_hashes = (
                [h for h in hashes if isinstance(h, str) and h in known]
                if isinstance(hashes, list)
                else []
            )
            confidence = str(item.get("confidence", "low")).lower()
            day.confidence = confidence if confidence in {"high", "medium", "low"} else "low"
        return CommitPlanDTO(
            summary=str(raw.get("summary", "")).strip(),
            days=days,
            raw_response=json.dumps(raw, ensure_ascii=False),
        )
```

- [ ] **Step 3: Extend TrackingService for commits and write**

В `TrackingService.__init__` добавьте:

```python
        self.git_client_factory = GitClient
        self.ai_client_factory = create_ai_client
```

В `_add_user_rows` добавьте ветку `COMMITS`:

```python
        if source is TrackingSource.COMMITS:
            from services.tracking_plan_service import TrackingPlanService
            from clients.ai.factory import create_ai_client

            if not project.git_repo_path:
                raise TrackingError("Не задан git-репозиторий проекта")
            if not user.git_email:
                raise TrackingError("Не задан git email юзера")
            if ai_settings is None:
                raise TrackingError("Не настроен AI")
            git = self.git_client_factory(project.git_repo_path)
            commits = git.list_commits(user.git_email, start, end)
            ai_client = self.ai_client_factory(ai_settings)
            plan = TrackingPlanService(ai_client, log=self.log).build_plan(
                project, user, destination_kind, existing, start, end, commits
            )
            for day in plan.days:
                report.rows.append(
                    TrackingRow(
                        row_id=f"{user.db_id}:{day.date}",
                        user_id=int(user.db_id),
                        user_name=user.name,
                        date=day.date,
                        existing_hours=day.existing_hours,
                        proposed_hours=day.planned_hours,
                        comment=day.comment or project.default_comment,
                        source_details=",".join(day.commit_hashes),
                        include=day.planned_hours > 0,
                    )
                )
            return
```

Реализуйте `write_report`:

```python
    def write_report(
        self, project: ProjectConfig, report: TrackingReport
    ) -> TrackingWriteResult:
        result = TrackingWriteResult()
        users = {user.db_id: user for user in project.users}
        for user_id, user in users.items():
            rows = [
                row for row in report.rows
                if row.user_id == user_id
                and row.include
                and row.proposed_hours > 0
                and not row.error
            ]
            if not rows:
                continue
            try:
                tracker = self._tracker(user, report.destination_kind)
                records = [
                    WorklogDTO(
                        date=row.date,
                        hours=row.proposed_hours,
                        description=row.comment or project.default_comment,
                    )
                    for row in rows
                ]
                errors = tracker.create_worklogs(records)
                errors_by_date = dict(errors)
                for row in rows:
                    if row.date in errors_by_date:
                        row.status = "ошибка"
                        row.error = errors_by_date[row.date]
                        result.errors.append(
                            (user.name, row.date, row.error)
                        )
                    else:
                        row.status = "записано"
                        row.include = False
                        result.written += 1
            except Exception as exc:
                result.errors.append((user.name, "", str(exc)))
        return result
```

- [ ] **Step 4: Run tests and full suite**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_tracking_service.py tests/test_tracking_write.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/tracking_plan_service.py services/tracking_service.py tests/test_tracking_service.py tests/test_tracking_write.py
git commit -m "feat: add commits source and tracking write"
```

---

### Task 7: Main window, project list and project menu

**Files:**
- Rewrite: `gui/app.py`
- Rewrite: `gui/project_list_view.py`
- Rewrite: `gui/project_view.py`
- Modify: `work_assistant.py`
- Modify: `tests/test_project_validation.py` (only if imports break)

**Interfaces:**
- Consumes: `ProjectRepository`, `SettingsRepository`, `GuiWorker`, `ProjectConfig`.
- Produces:
  - `MainWindow(repo, settings_repo)`
  - `ProjectListView(parent, repo, on_open)`
  - `ProjectView(parent, project, repo, settings_repo, worker, on_back, on_tracking)`

- [ ] **Step 1: Rewrite ProjectListView**

```python
# gui/project_list_view.py
from collections.abc import Callable
from tkinter import messagebox, simpledialog, ttk

from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class ProjectListView(ttk.Frame):
    def __init__(
        self,
        parent,
        repo: ProjectRepository,
        settings_repo: SettingsRepository,
        on_open: Callable[[ProjectConfig], None],
        on_ai_settings: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self.repo = repo
        self.settings_repo = settings_repo
        self.on_open = on_open
        self.on_ai_settings = on_ai_settings
        self.projects_by_iid: dict[str, ProjectConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Добавить", command=self.add_project).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Удалить", command=self.delete_project).pack(
            side="left", padx=2
        )
        ttk.Button(
            toolbar, text="Настройки AI", command=self.on_ai_settings
        ).pack(side="right", padx=2)

        self.tree = ttk.Treeview(
            self, columns=("name",), show="headings", height=16
        )
        self.tree.heading("name", text="Проект")
        self.tree.column("name", width=700, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda event: self.open_project())
        self.tree.bind("<Return>", lambda event: self.open_project())
        self.empty = ttk.Label(
            self, text="Нажмите «Добавить», чтобы создать проект", foreground="#777"
        )
        self.empty.pack(anchor="w")

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.projects_by_iid.clear()
        projects = self.repo.list_projects()
        for project in projects:
            iid = self.tree.insert("", "end", values=(project.name,))
            self.projects_by_iid[iid] = project
        if projects:
            self.empty.pack_forget()
        else:
            self.empty.pack(anchor="w")

    def selected_project(self, show: bool = True) -> ProjectConfig | None:
        selection = self.tree.selection()
        if not selection:
            if show:
                messagebox.showinfo("Work Assistant", "Выберите проект", parent=self)
            return None
        return self.projects_by_iid[selection[0]]

    def add_project(self) -> None:
        name = simpledialog.askstring("Новый проект", "Имя проекта:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if self.repo.find_by_name(name) is not None:
            messagebox.showerror("Work Assistant", "Проект с таким именем уже есть", parent=self)
            return
        project_id = self.repo.add_project(ProjectConfig(name=name))
        project = self.repo.get_project(project_id)
        self.refresh()
        if project is not None:
            self.on_open(project)

    def delete_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        if messagebox.askyesno(
            "Work Assistant", f"Удалить проект «{project.name}»?", parent=self
        ):
            self.repo.delete_project(project.db_id)
            self.refresh()

    def open_project(self) -> None:
        project = self.selected_project(show=False)
        if project is not None:
            self.on_open(project)
```

- [ ] **Step 2: Rewrite ProjectView**

```python
# gui/project_view.py
from collections.abc import Callable
from tkinter import ttk

from configs.project_config import ProjectConfig
from gui.worker import GuiWorker
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class ProjectView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        settings_repo: SettingsRepository,
        worker: GuiWorker,
        on_back: Callable[[], None],
        on_tracking: Callable[[ProjectConfig], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = worker
        self.on_back = on_back
        self.on_tracking = on_tracking

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(header, text="← Проекты", command=self.on_back).pack(side="left")
        ttk.Label(
            header, text=project.name, font=("TkDefaultFont", 14, "bold")
        ).pack(side="left", padx=12)

        menu = ttk.LabelFrame(self, text="Меню", padding=8)
        menu.pack(fill="x", pady=12)
        ttk.Button(
            menu,
            text="Трекинг времени",
            command=lambda: self.on_tracking(self.project),
        ).pack(anchor="w")

    @property
    def busy(self) -> bool:
        return False
```

- [ ] **Step 3: Rewrite MainWindow and entry point**

```python
# gui/app.py
import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_list_view import ProjectListView
from gui.project_view import ProjectView
from gui.worker import GuiWorker
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class MainWindow(tk.Tk):
    def __init__(
        self, repo: ProjectRepository, settings_repo: SettingsRepository
    ) -> None:
        super().__init__()
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = GuiWorker(self)
        self.current_view: tk.Widget | None = None

        self.title("Work Assistant")
        self.geometry("1100x780")
        self.minsize(900, 620)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self, textvariable=self.status, relief="sunken", anchor="w", padding=2
        ).pack(fill="x", side="bottom")
        self.worker.register("status", self._set_status)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_project_list()

    def _set_status(self, message: str) -> None:
        self.status.set(message)

    def _drop_view(self) -> None:
        if self.current_view is not None:
            self.current_view.destroy()
            self.current_view = None

    def _set_view(self, view: tk.Widget) -> None:
        self._drop_view()
        self.current_view = view
        view.pack(fill="both", expand=True)

    def show_project_list(self) -> None:
        self._drop_view()
        self.status.set("готово")
        self._set_view(
            ProjectListView(
                self.container,
                self.repo,
                self.settings_repo,
                on_open=self.show_project,
                on_ai_settings=self.show_ai_settings,
            )
        )

    def show_project(self, project: ProjectConfig) -> None:
        self._drop_view()
        self._set_view(
            ProjectView(
                self.container,
                project=project,
                repo=self.repo,
                settings_repo=self.settings_repo,
                worker=self.worker,
                on_back=self.show_project_list,
                on_tracking=self.show_tracking,
            )
        )

    def show_tracking(self, project: ProjectConfig) -> None:
        self.status.set("трекинг времени — в следующем шаге")

    def show_ai_settings(self) -> None:
        self.status.set("настройки AI — в следующем шаге")

    def _on_close(self) -> None:
        busy = bool(getattr(self.current_view, "busy", False))
        if busy and not messagebox.askyesno(
            "Work Assistant", "Работа выполняется. Закрыть окно?", parent=self
        ):
            return
        self.destroy()
```

```python
# work_assistant.py
from gui.app import MainWindow
from storage.database import migrate_default_legacy_database
from storage.migration import (
    migrate_from_user_list,
    migrate_projects_to_v2,
    migrate_users_to_projects,
)
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository
from storage.user_repository import UserRepository


def main() -> None:
    migrate_default_legacy_database(log=print)
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    settings_repo = SettingsRepository()
    migrate_from_user_list(user_repo, log=print)
    migrate_users_to_projects(project_repo, user_repo, log=print)
    migrate_projects_to_v2(project_repo, settings_repo, log=print)
    app = MainWindow(project_repo, settings_repo)
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile gui/app.py gui/project_list_view.py gui/project_view.py work_assistant.py`
Expected: exit 0.

```bash
git add gui/app.py gui/project_list_view.py gui/project_view.py work_assistant.py
git commit -m "feat: add project-centric main window"
```

---

### Task 8: Global AI settings dialog

**Files:**
- Create: `gui/ai_settings_validation.py`
- Create: `gui/ai_settings_dialog.py`
- Modify: `gui/app.py`
- Create: `tests/test_ai_settings_validation.py`

**Interfaces:**
- Consumes: `AiSettings`, `SettingsRepository`, `GuiWorker`, `create_ai_client`.
- Produces:
  - `validate_ai_settings(provider, model, base_url, keys) -> tuple[AiSettings | None, list[str]]`
  - `AiSettingsDialog(parent, settings_repo, worker)`

- [ ] **Step 1: Write failing validation test**

```python
# tests/test_ai_settings_validation.py
from gui.ai_settings_validation import validate_ai_settings


def test_valid_settings():
    settings, errors = validate_ai_settings(
        provider="openai",
        model="gpt",
        base_url="",
        keys={"openai": "key"},
    )
    assert errors == []
    assert settings.provider == "openai"
    assert settings.keys["openai"] == "key"


def test_openai_requires_key():
    settings, errors = validate_ai_settings(
        provider="openai", model="gpt", base_url="", keys={}
    )
    assert settings is None
    assert any("ключ" in error.lower() for error in errors)


def test_custom_requires_base_url():
    settings, errors = validate_ai_settings(
        provider="custom",
        model="model",
        base_url="",
        keys={"custom": "key"},
    )
    assert settings is None
    assert any("base_url" in error for error in errors)
```

- [ ] **Step 2: Implement validation and dialog**

```python
# gui/ai_settings_validation.py
from configs.ai_settings import AiSettings

PROVIDERS = ("opencode_go", "openai", "anthropic", "custom")


def validate_ai_settings(
    provider: str,
    model: str,
    base_url: str,
    keys: dict[str, str],
) -> tuple[AiSettings | None, list[str]]:
    errors: list[str] = []
    if provider not in PROVIDERS:
        errors.append("Неизвестный провайдер")
    if not model.strip():
        errors.append("Выберите модель")
    if not keys.get(provider, "").strip():
        errors.append(f"Не задан API-ключ для {provider}")
    if provider == "custom" and not base_url.strip():
        errors.append("Для custom нужен base_url")
    if errors:
        return None, errors
    return (
        AiSettings(
            provider=provider,
            model=model.strip(),
            base_url=base_url.strip(),
            keys={k: v.strip() for k, v in keys.items() if v.strip()},
        ),
        [],
    )
```

`gui/ai_settings_dialog.py` — диалог:

- Поля: provider combobox, model combobox + «Обновить модели», API key (secret), base URL (только custom), кнопки «Проверить подключение», «Сохранить», «Отмена».
- Загружает `settings_repo.get_ai_settings()`.
- При смене провайдера показывает сохранённый ключ из `keys`.
- «Обновить модели»:
  - собирает текущие значения, валидирует;
  - в worker (`self.worker.submit`) создаёт `create_ai_client(settings)` и вызывает `list_models()`;
  - событие `ai_models_done` заполняет combobox;
  - ошибка — `messagebox` + лог.
- «Проверить подключение» аналогично вызывает `check_connection()`.
- «Сохранить» валидирует, `settings_repo.save_ai_settings`, закрывает.
- Уникальные worker-события: `ai_models_done`, `ai_check_done`, `ai_error`; зарегистрировать и снять в `destroy`.

В `MainWindow.show_ai_settings`:

```python
    def show_ai_settings(self) -> None:
        dialog = AiSettingsDialog(self, self.settings_repo, self.worker)
        self.wait_window(dialog)
        self.status.set("настройки AI сохранены")
```

В `__init__` MainWindow импортировать `AiSettingsDialog`.

- [ ] **Step 3: Run tests and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_ai_settings_validation.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile gui/ai_settings_dialog.py gui/ai_settings_validation.py gui/app.py`
Expected: exit 0.

```bash
git add gui/ai_settings_dialog.py gui/ai_settings_validation.py gui/app.py tests/test_ai_settings_validation.py
git commit -m "feat: add global AI settings dialog"
```

---

### Task 9: Project settings panel and user editor

**Files:**
- Create: `gui/settings_validation.py`
- Create: `gui/user_editor.py`
- Create: `gui/project_settings_panel.py`
- Create: `tests/test_settings_validation.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `ProjectUserConfig`, `ProjectRepository`, `all_trackers`.
- Produces:
  - `validate_project_settings(form, exclude_dates) -> tuple[ProjectConfig | None, list[str]]`
  - `validate_user_settings(name, git_email, tracker_values) -> tuple[ProjectUserConfig | None, list[str]]`
  - `UserEditor(parent, user=None)`
  - `ProjectSettingsPanel(parent, project, repo, on_saved)`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_settings_validation.py
from gui.settings_validation import validate_project_settings, validate_user_settings


def test_project_settings_valid():
    project, errors = validate_project_settings(
        {"git_repo_path": "/repo", "workday_hours": "8", "default_comment": "development"},
        exclude_dates=["2026-10-05"],
    )
    assert errors == []
    assert project.workday_hours == 8
    assert project.default_comment == "development"


def test_project_settings_reject_empty_comment():
    project, errors = validate_project_settings(
        {"workday_hours": "8", "default_comment": ""}, []
    )
    assert project is None
    assert any("комментарий" in error.lower() for error in errors)


def test_user_settings_valid():
    user, errors = validate_user_settings(
        "Олег",
        "me@example.com",
        {"redmine": {"api_key": "key", "user_id": "16", "activity_id": "9", "issue_id": "2682"}},
    )
    assert errors == []
    assert user.name == "Олег"
    assert user.trackers["redmine"]["user_id"] == 16


def test_user_settings_partial_tracker_rejected():
    user, errors = validate_user_settings(
        "Олег", "", {"redmine": {"api_key": "key"}}
    )
    assert user is None
    assert any("Redmine" in error for error in errors)
```

- [ ] **Step 2: Implement validation and user editor**

```python
# gui/settings_validation.py
from configs.project_config import ProjectConfig, ProjectUserConfig
from trackers.registry import all_trackers


def validate_project_settings(
    form: dict[str, str], exclude_dates: list[str]
) -> tuple[ProjectConfig | None, list[str]]:
    errors: list[str] = []
    try:
        workday = float(form.get("workday_hours", "8"))
    except (TypeError, ValueError):
        errors.append("Рабочий день: должно быть числом")
        workday = 8.0
    if not 0 < workday <= 24:
        errors.append("Рабочий день: больше 0 и не больше 24")
    comment = form.get("default_comment", "development").strip()
    if not comment:
        errors.append("Комментарий по умолчанию обязателен")
    if errors:
        return None, errors
    return (
        ProjectConfig(
            name="",
            git_repo_path=form.get("git_repo_path", "").strip(),
            workday_hours=workday,
            exclude_dates=sorted(exclude_dates),
            default_comment=comment,
        ),
        [],
    )


def _int_value(value, label: str, errors: list[str]) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_user_settings(
    name: str,
    git_email: str,
    tracker_values: dict[str, dict],
) -> tuple[ProjectUserConfig | None, list[str]]:
    errors: list[str] = []
    name = name.strip()
    if not name:
        errors.append("Имя юзера обязательно")
    if git_email and "@" not in git_email:
        errors.append("git email выглядит некорректно")

    trackers: dict[str, dict] = {}
    for cls in all_trackers():
        values = tracker_values.get(cls.kind, {})
        cls_errors = cls.validate_config(values)
        errors.extend(cls_errors)
        if cls_errors:
            continue
        if not any(
            values.get(field.key) not in (None, "")
            for field in cls.fields
            if field.required
        ):
            continue
        config: dict = {}
        for field in cls.fields:
            raw = values.get(field.key, "")
            if raw in (None, ""):
                continue
            if field.kind == "int":
                config[field.key] = _int_value(raw, f"{cls.label}: {field.label}", errors)
            else:
                config[field.key] = str(raw).strip()
        trackers[cls.kind] = config

    if errors:
        return None, errors
    return (
        ProjectUserConfig(
            name=name,
            git_email=git_email.strip(),
            trackers=trackers,
        ),
        [],
    )
```

`gui/user_editor.py`:

- Диалог `UserEditor(parent, user=None)`.
- Поля: имя, git email, динамические секции `all_trackers()`.
- Секреты маскируются, чекбокс «показать секреты».
- Сохранение через `validate_user_settings`; результат в `self.result`.
- Использовать `ttk.Notebook` или scrollable frame; секции трекеров.
- Кнопки «Сохранить»/«Отмена», инлайн-ошибки.

`gui/project_settings_panel.py`:

- `ttk.LabelFrame` с полями проекта, списком юзеров и кнопками.
- Поля: git path + browse, workday, default comment, exclude dates list.
- Таблица юзеров: `☑` (для выбора в трекинге), имя, email, Redmine/YouTrack статус.
- Кнопки: добавить/изменить/удалить юзера, импорт из проекта, сохранить.
- `selected_user_ids()` — список выбранных.
- `save()`:
  - `validate_project_settings`;
  - `repo.update_project(project.db_id, project)`;
  - `repo.replace_users(project.db_id, users)`;
  - `on_saved(repo.get_project(project.db_id))`.
- Импорт:
  - диалог выбора проекта-донора (`simpledialog`/`Toplevel` со списком);
  - `repo.merge_users_from(project.db_id, donor)`;
  - перезагрузить панель.
- Внутри панели хранить `self.users: list[ProjectUserConfig]`, флаги выбора в `self.selected_vars`.
- `UserEditor` вызывается модально.

- [ ] **Step 3: Run tests and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_settings_validation.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile gui/settings_validation.py gui/user_editor.py gui/project_settings_panel.py`
Expected: exit 0.

`ProjectSettingsPanel` после `validate_project_settings` должен проставить текущие `name` и `db_id` проекта:

```python
project.name = self.project.name
project.db_id = self.project.db_id
```

Затем `repo.update_project(project.db_id, project)`, `repo.replace_users(project.db_id, self.users)`, `self.project = repo.get_project(project.db_id)`, `on_saved(self.project)`.

Ключевые методы: `selected_user_ids()`, `save()`, `add_user()`, `edit_user()`, `delete_user()`, `import_from_project()`, `reload()`.

Перед сохранением проверить уникальность имён юзеров в проекте; при конфликте показать ошибку и не писать в БД.

- [ ] **Step 4: Commit**

```bash
git add gui/settings_validation.py gui/user_editor.py gui/project_settings_panel.py tests/test_settings_validation.py
git commit -m "feat: add project settings panel and user editor"
```

---

### Task 10: Tracking view and report generation

**Files:**
- Create: `gui/tracking_validation.py`
- Create: `gui/tracking_view.py`
- Modify: `gui/project_view.py`
- Modify: `gui/app.py`
- Create: `tests/test_tracking_validation.py`

**Interfaces:**
- Consumes: `TrackingService`, `TrackingSource`, `ProjectSettingsPanel`, `ProjectConfig`.
- Produces:
  - `validate_tracking_request(user_ids, destination, source, source_kind, start_text, end_text) -> tuple[dict | None, list[str]]`
  - `trackers_for_project(project) -> list[type[BaseTracker]]`
  - `TrackingView(parent, project, repo, settings_repo, worker, on_back)`

- [ ] **Step 1: Write failing validation tests**

```python
# tests/test_tracking_validation.py
from gui.tracking_validation import validate_tracking_request


def test_valid_request():
    data, errors = validate_tracking_request(
        user_ids=[1],
        destination="redmine",
        source="autofill",
        source_kind="",
        start_text="2026-10-01",
        end_text="2026-10-31",
    )
    assert errors == []
    assert data["destination"] == "redmine"
    assert data["start"].isoformat() == "2026-10-01"


def test_requires_users():
    data, errors = validate_tracking_request(
        [], "redmine", "autofill", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("юзера" in error.lower() for error in errors)


def test_tracker_source_cannot_equal_destination():
    data, errors = validate_tracking_request(
        [1], "redmine", "tracker", "redmine", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("совпадать" in error.lower() for error in errors)


def test_bad_period():
    data, errors = validate_tracking_request(
        [1], "redmine", "autofill", "", "2026-10-31", "2026-10-01"
    )
    assert data is None
    assert any("позже" in error.lower() for error in errors)
```

- [ ] **Step 2: Implement validation and TrackingView**

```python
# gui/tracking_validation.py
from datetime import date


def validate_tracking_request(
    user_ids: list[int],
    destination: str,
    source: str,
    source_kind: str,
    start_text: str,
    end_text: str,
) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not user_ids:
        errors.append("Выберите хотя бы одного юзера")
    if not destination:
        errors.append("Выберите трекер-назначение")
    if not source:
        errors.append("Выберите источник")
    if source == "tracker":
        if not source_kind:
            errors.append("Выберите трекер-источник")
        elif source_kind == destination:
            errors.append("Источник и назначение не могут совпадать")
    try:
        start = date.fromisoformat(start_text.strip())
        end = date.fromisoformat(end_text.strip())
    except ValueError:
        errors.append("Даты должны быть в формате ГГГГ-ММ-ДД")
        start = end = None
    if start and end and start > end:
        errors.append("Начало периода позже конца")
    if errors:
        return None, errors
    return (
        {
            "user_ids": list(user_ids),
            "destination": destination,
            "source": source,
            "source_kind": source_kind,
            "start": start,
            "end": end,
        },
        [],
    )
```

`gui/tracking_view.py` — ключевая структура:

```python
from trackers.registry import all_trackers


def trackers_for_project(project) -> list[type]:
    kinds = {
        kind
        for user in project.users
        for kind, config in user.trackers.items()
        if config
    }
    return [
        cls for cls in all_trackers()
        if cls.kind in kinds and cls.can_read
    ]


class TrackingView(ttk.Frame):
    def __init__(self, parent, project, repo, settings_repo, worker, on_back):
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = worker
        self.on_back = on_back
        self.report: TrackingReport | None = None
        self.busy = False
        self.tracker_vars = {}
        self.service = TrackingService(log=self._log_from_worker)
        self.rows_by_iid: dict[str, TrackingRow] = {}
        self._build()
        self._register_handlers()

    def _log_from_worker(self, message: str) -> None:
        self.worker.send("tracking_log", message)
```

- Header: back, title.
- `ProjectSettingsPanel` сверху, collapsible (можно `ttk.LabelFrame` + кнопка свернуть/развернуть).
- Controls:
  - destination combobox: `trackers_for_project(project)` (объединение настроенных трекеров юзеров).
  - source combobox: `Автозаполнение`, `Из трекера`, `Из коммитов`.
  - source tracker combobox: только если source=tracker; список kind != destination.
  - period entries, default current month.
  - generate button.
- Report Treeview columns: include, user, date, existing, proposed, comment, source/status.
- Buttons: «Затрекать» (Task 11), log Text.
- `_generate`:
  - gather selected user ids from settings panel.
  - validate.
  - `ai_settings = self.settings_repo.get_ai_settings()` (передать сервису; для не-коммитов он не используется).
  - `self._set_busy(True)`;
  - `self.worker.submit(lambda: self.service.generate_report(...), done_kind="tracking_report_done", error_kind="tracking_error")`.
- `_on_report_done`: fill tree, store report, enable write.
- `_on_error`: messagebox + log.
- `_set_busy`.
- `destroy`: unregister handlers.
- `log` method (Tk `Text`, main thread).
- `busy` property.
- `_register_handlers`: `tracking_report_done`, `tracking_error`, `tracking_log`; `tracking_log` handler вызывает `self.log` на главном потоке.
- `refresh_trackers()`: destination/source lists based on project users.
- `ProjectSettingsPanel.on_saved` callback reloads project and refreshes tracker lists.

`ProjectView` changes:
- Add `on_tracking` callback; already. `MainWindow.show_tracking` creates `TrackingView` with `ProjectSettingsPanel`.
- `MainWindow.show_tracking(project)`:
```python
    def show_tracking(self, project: ProjectConfig) -> None:
        self._drop_view()
        self._set_view(
            TrackingView(
                self.container, project, self.repo, self.settings_repo,
                self.worker, on_back=lambda: self.show_project(project),
            )
        )
```

- [ ] **Step 3: Run tests and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_tracking_validation.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile gui/tracking_validation.py gui/tracking_view.py gui/project_view.py gui/app.py`
Expected: exit 0.

```bash
git add gui/tracking_validation.py gui/tracking_view.py gui/project_view.py gui/app.py tests/test_tracking_validation.py
git commit -m "feat: add tracking view and report generation"
```

---

### Task 11: Report editor and write wiring

**Files:**
- Create: `gui/report_editor.py`
- Modify: `gui/tracking_view.py`
- Create: `tests/test_report_editor_validation.py`

**Interfaces:**
- Consumes: `TrackingRow`, `TrackingService.write_report`.
- Produces:
  - `validate_report_row(hours_text, comment) -> tuple[float | None, list[str]]`
  - `ReportEditor(parent, row)`

- [ ] **Step 1: Write failing validation tests**

```python
# tests/test_report_editor_validation.py
from gui.report_editor import validate_report_row


def test_valid_row():
    hours, errors = validate_report_row("4", "development")
    assert errors == []
    assert hours == 4


def test_half_step_required():
    hours, errors = validate_report_row("4.3", "development")
    assert hours is None
    assert any("0.5" in error for error in errors)


def test_comment_defaults():
    hours, errors = validate_report_row("4", "  ")
    assert errors == []
    assert hours == 4
```

- [ ] **Step 2: Implement report editor and write**

```python
# gui/report_editor.py
import tkinter as tk
from tkinter import ttk

from dto.tracking_dto import TrackingRow


def validate_report_row(
    hours_text: str, comment: str
) -> tuple[float | None, list[str]]:
    try:
        hours = float(hours_text.replace(",", ".").strip())
    except ValueError:
        return None, ["Часы должны быть числом"]
    if hours <= 0:
        return None, ["Часы должны быть больше нуля"]
    if hours > 24:
        return None, ["Часы не могут быть больше 24"]
    if abs(hours * 2 - round(hours * 2)) > 1e-9:
        return None, ["Часы должны быть кратны 0.5"]
    return hours, []


class ReportEditor(tk.Toplevel):
    def __init__(self, parent, row: TrackingRow):
        super().__init__(parent)
        self.row = row
        self.result = False
        self.title("Редактировать строку")
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{row.user_name} — {row.date}").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, text="Часы").grid(row=1, column=0, sticky="w")
        self.hours = ttk.Entry(frame, width=12)
        self.hours.grid(row=1, column=1, sticky="we")
        self.hours.insert(0, f"{row.proposed_hours:g}")
        ttk.Label(frame, text="Комментарий").grid(row=2, column=0, sticky="w")
        self.comment = ttk.Entry(frame, width=40)
        self.comment.grid(row=2, column=1, sticky="we")
        self.comment.insert(0, row.comment)
        self.include = tk.BooleanVar(value=row.include)
        ttk.Checkbutton(frame, text="включить в трек", variable=self.include).grid(
            row=3, column=1, sticky="w", pady=4
        )
        self.error = ttk.Label(frame, text="", foreground="red", wraplength=360)
        self.error.grid(row=4, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Сохранить", command=self._save).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="left")
        self.transient(parent)
        self.grab_set()

    def _save(self) -> None:
        hours, errors = validate_report_row(self.hours.get(), self.comment.get())
        if errors:
            self.error.configure(text="\n".join(errors))
            return
        self.row.proposed_hours = hours
        self.row.comment = self.comment.get().strip() or "development"
        self.row.include = self.include.get()
        self.result = True
        self.destroy()
```

В `TrackingView`:

- Добавить кнопку «Затрекать» и `write` handler.
- `self.write_button` disabled until report.
- Двойной клик по строке:
```python
    def _edit_row(self, event=None) -> None:
        selection = self.report_tree.selection()
        if not selection or self.report is None:
            return
        row = self.rows_by_iid.get(selection[0])
        if row is None:
            return
        editor = ReportEditor(self, row)
        self.wait_window(editor)
        if editor.result:
            self._refresh_row(selection[0], row)
```
- Space toggles include:
```python
    def _toggle_row(self, event=None) -> None:
        selection = self.report_tree.selection()
        if not selection:
            return
        row = self.rows_by_iid[selection[0]]
        row.include = not row.include
        self._refresh_row(selection[0], row)
```
- `_refresh_row(iid, row)`: update values, tag "excluded" maybe.
- `write`:
```python
    def _write(self) -> None:
        if self.report is None:
            return
        selected = [row for row in self.report.rows if row.include and row.proposed_hours > 0]
        if not selected:
            messagebox.showinfo("Work Assistant", "Нет строк для записи", parent=self)
            return
        total = sum(row.proposed_hours for row in selected)
        if not messagebox.askyesno(
            "Work Assistant",
            f"Записать {len(selected)} строк ({total:g} ч)?",
            parent=self,
        ):
            return
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.write_report(self.project, self.report),
            done_kind="tracking_write_done",
            error_kind="tracking_error",
        )
```
- `_on_write_done`: log result, refresh all rows, messagebox summary.
- `_register_handlers`: `tracking_report_done`, `tracking_write_done`, `tracking_error`, `tracking_log`.
- `destroy`: unregister exact handlers.
- Need `rows_by_iid`.

- [ ] **Step 3: Run tests and commit**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest tests/test_report_editor_validation.py -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile gui/report_editor.py gui/tracking_view.py`
Expected: exit 0.

```bash
git add gui/report_editor.py gui/tracking_view.py tests/test_report_editor_validation.py
git commit -m "feat: add editable report and tracking write"
```

---

### Task 12: Remove old flows, update docs, final verification

**Files:**
- Delete: `work_assistant_cli.py`, `fill_redmine.py`
- Delete: `imports/` (all files)
- Delete: `services/import_service.py`, `services/preview_service.py`, `services/issue_service.py`, `services/commit_plan_service.py`
- Delete: `gui/import_view.py`, `gui/commit_plan_view.py`, `gui/project_editor.py`, `gui/project_validation.py`, `gui/import_view_helpers.py` test, old CLI/import/preview/commit-plan tests
- Delete: `dto/preview_dto.py`, `dto/date_hours_dto.py`, `dto/issue_info_dto.py`, `dto/import_action.py`
- Delete: `clients/ai_client.py` (old), `tests/test_ai_client.py`
- Modify: `clients/redmine_client.py` — remove old async/XML methods and `DateHoursDTO` import; keep `get_time_entries` and `create_time_entries_sync`
- Modify: `gui/formatting.py` — remove `DateRangeDTO` formatting; keep/use `format_hours`
- Modify: `tests/test_gui_formatting.py` — update to new helpers
- Modify: `README.md`
- Modify: `.env.example`
- Modify: `work_assistant.py` (already v2)
- Modify: `.gitignore` if needed

**Keep:**
- `configs/user_config.py`, `storage/user_repository.py`, `storage/migration.py` — legacy user_list migration.
- `gui/validation.py` — `parse_exclude_date`; keep or move.
- `tests/test_user_config.py`, `test_user_repository.py`, `test_migration.py`.
- `services/commit_plan_service.py` — replaced by `tracking_plan_service.py`; delete old.

- [ ] **Step 1: Remove old modules and tests**

Use `git rm` for the files listed above. Before deleting, run:

```bash
grep -R "imports\.\|import_service\|preview_service\|issue_service\|commit_plan_service\|ai_client\|date_hours_dto\|preview_dto\|import_action" --include="*.py" .
```

Update any live imports to new modules. Expected live references only in files being deleted or legacy tests.

In `clients/redmine_client.py` remove `create_time_entries`, `create_time_entry`, `get_spent_on_dates` and the `DateHoursDTO` import; keep `get_issue` only if still used, otherwise remove it too. The new read path is `get_time_entries`, the new write path is `create_time_entries_sync`.

In `gui/formatting.py` keep `format_hours`; remove `format_range`/`format_ranges` and the `DateRangeDTO` import. Update `tests/test_gui_formatting.py` to test `format_hours` only (or remove the old range tests).

- [ ] **Step 2: Update README and .env**

README must document:

- project list, add/delete, settings AI;
- project → tracking;
- users with keys + git email;
- destination/source/period;
- report editing and write;
- global AI providers (OpenCode Go / OpenAI / Anthropic / Custom), OpenCode Go API key/base URL;
- no CLI;
- migration from old DB;
- adding a new tracker.

`.env.example`:

```dotenv
REDMINE_BASE_URL=https://redmine.org
YOUTRACK_BASE_URL=https://youtrack.cloud
WORK_ASSISTANT_DB=
```

- [ ] **Step 3: Run full verification**

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m pytest -q`
Expected: PASS.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -m py_compile work_assistant.py fill_redmine_gui.py gui/*.py services/*.py clients/*.py clients/ai/*.py trackers/*.py storage/*.py configs/*.py dto/*.py`
Expected: exit 0.

Run: `/home/oleg/code/fill_redmine/.venv/bin/python -c "import work_assistant"`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy import flows and document tracking v2"
```

---

## Self-Review

**Spec coverage:**

- Projects + users + per-user keys: Task 1, 9.
- Global AI settings: Task 2, 4, 8.
- OpenCode Go/OpenAI/Anthropic/Custom: Task 4.
- Tracker writes Redmine/YouTrack: Task 3.
- Autofill: Task 5.
- From tracker: Task 5.
- From commits + AI: Task 6.
- Editable report: Task 10, 11.
- Write only included rows: Task 6, 11.
- Project settings panel + import from project: Task 9.
- Main screen only projects + add/delete: Task 7.
- Project menu tracking: Task 7, 10.
- CLI removal: Task 12.
- Migration v2: Task 2, 7.
- Tests: every task.

**Type consistency:**

- `ProjectUserConfig` from Task 1 used in Tasks 2, 5, 6, 9.
- `AiSettings` from Task 2 used in Tasks 4, 8.
- `TrackingRow`, `TrackingReport`, `TrackingSource` from Task 5 used in Tasks 6, 10, 11.
- `TrackingService` from Task 5 extended in Task 6, used in Task 10/11.
- `create_ai_client`, `AiClient` from Task 4 used in Task 6/8.
- `BaseTracker.create_worklogs` from Task 3 used in Task 6.
- `ProjectSettingsPanel.selected_user_ids()` from Task 9 used in Task 10.
