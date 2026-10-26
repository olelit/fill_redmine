# Work Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переименовать Fill Redmine в Work Assistant и добавить проекты с тремя сценариями: заполнение Redmine, перенос YouTrack → Redmine и ИИ-план по git-коммитам.

**Architecture:** Проект хранится в SQLite и содержит JSON-конфиги трекеров и ИИ. Трекеры описывают свои поля и реализуют чтение worklog'ов; GUI строит формы и список чекбоксов автоматически. Импорт и расчёт дефицита — отдельные сервисы, git и ИИ — отдельные клиенты.

**Tech Stack:** Python 3.10+, Tkinter/ttk, SQLite, requests, aiohttp, pytest.

## Global Constraints

- Новые зависимости не добавлять: уже есть `requests`, `aiohttp`, `python-dotenv`.
- Все новые публичные функции и методы — с type hints.
- Импорты абсолютные, порядок: stdlib → third-party → локальные.
- Пользовательские строки GUI — на русском; технические поля — как в коде.
- Секреты в UI маскировать, в SQLite — открытый текст (как раньше).
- В YouTrack ничего не записывать: только предлагать план и копировать текст.
- Корневую папку репозитория не переименовывать.
- Каждая задача заканчивается зелёными тестами и отдельным коммитом.
- Перед коммитом проверять: `pytest -q`.

---

### Task 1: ProjectConfig, схема БД и ProjectRepository

**Files:**
- Create: `configs/project_config.py`
- Create: `storage/project_repository.py`
- Create: `tests/test_project_repository.py`
- Create: `tests/test_database.py`
- Modify: `storage/database.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `ProjectConfig(name, git_repo_path="", git_author_email="", workday_hours=8.0, exclude_dates=[], trackers={}, ai={}, db_id=None)`
  - `ProjectRepository.list_projects() -> list[ProjectConfig]`
  - `ProjectRepository.get_project(db_id: int) -> ProjectConfig | None`
  - `ProjectRepository.find_by_name(name: str) -> ProjectConfig | None`
  - `ProjectRepository.add_project(project) -> int`
  - `ProjectRepository.add_projects(projects: list[ProjectConfig]) -> None`
  - `ProjectRepository.update_project(db_id: int, project) -> None`
  - `ProjectRepository.delete_project(db_id: int) -> None`
  - `ProjectRepository.get_meta(key: str) -> str | None`
  - `ProjectRepository.set_meta(key: str, value: str) -> None`
  - `get_default_db_path() -> Path`, `get_legacy_db_path() -> Path`, `migrate_default_legacy_database(log=print) -> bool`

- [ ] **Step 1: Write failing repository tests**

```python
# tests/test_project_repository.py
import sqlite3

import pytest

from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        git_repo_path="/tmp/repo",
        git_author_email="me@example.com",
        workday_hours=8.0,
        exclude_dates=["2026-10-05"],
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            },
            "youtrack": {"access_token": "token"},
        },
        ai={
            "base_url": "https://api.example/v1",
            "model": "model",
            "api_key": "ai-key",
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


@pytest.fixture
def repo(tmp_path):
    return ProjectRepository(db_path=tmp_path / "test.db")


def test_list_projects_returns_empty_for_new_db(repo):
    assert repo.list_projects() == []


def test_add_and_list_roundtrip(repo):
    db_id = repo.add_project(make_project())

    projects = repo.list_projects()

    assert db_id == 1
    assert len(projects) == 1
    assert projects[0].name == "Проект"
    assert projects[0].git_repo_path == "/tmp/repo"
    assert projects[0].git_author_email == "me@example.com"
    assert projects[0].workday_hours == 8.0
    assert projects[0].exclude_dates == ["2026-10-05"]
    assert projects[0].trackers["redmine"]["issue_id"] == 2682
    assert projects[0].trackers["youtrack"]["access_token"] == "token"
    assert projects[0].ai["model"] == "model"
    assert projects[0].db_id == db_id


def test_get_project_returns_none_for_missing(repo):
    assert repo.get_project(999) is None


def test_find_by_name(repo):
    repo.add_project(make_project(name="Alpha"))

    assert repo.find_by_name("Alpha").db_id == 1
    assert repo.find_by_name("Missing") is None


def test_update_changes_fields(repo):
    db_id = repo.add_project(make_project())

    repo.update_project(db_id, make_project(name="Beta", workday_hours=7.5))

    project = repo.get_project(db_id)
    assert project.name == "Beta"
    assert project.workday_hours == 7.5


def test_update_missing_raises(repo):
    with pytest.raises(ValueError):
        repo.update_project(999, make_project())


def test_delete_project(repo):
    db_id = repo.add_project(make_project())

    repo.delete_project(db_id)

    assert repo.list_projects() == []


def test_duplicate_name_raises(repo):
    repo.add_project(make_project(name="Alpha"))

    with pytest.raises(sqlite3.IntegrityError):
        repo.add_project(make_project(name="Alpha"))


def test_add_projects_inserts_multiple(repo):
    repo.add_projects([make_project(name="Alpha"), make_project(name="Beta")])

    assert [p.name for p in repo.list_projects()] == ["Alpha", "Beta"]


def test_meta_roundtrip(repo):
    assert repo.get_meta("missing") is None

    repo.set_meta("legacy_users_migrated", "1")

    assert repo.get_meta("legacy_users_migrated") == "1"
```

```python
# tests/test_database.py
from pathlib import Path

from storage.database import (
    get_default_db_path,
    migrate_default_legacy_database,
    migrate_legacy_database,
)


def test_new_env_has_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("WORK_ASSISTANT_DB", str(tmp_path / "new.db"))
    monkeypatch.setenv("FILL_REDMINE_DB", str(tmp_path / "old.db"))

    assert get_default_db_path() == tmp_path / "new.db"


def test_legacy_env_is_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_ASSISTANT_DB", raising=False)
    monkeypatch.setenv("FILL_REDMINE_DB", str(tmp_path / "old.db"))

    assert get_default_db_path() == tmp_path / "old.db"


def test_default_name_is_work_assistant(monkeypatch):
    monkeypatch.delenv("WORK_ASSISTANT_DB", raising=False)
    monkeypatch.delenv("FILL_REDMINE_DB", raising=False)

    assert get_default_db_path().name == "work_assistant.db"


def test_migrate_legacy_database_renames_file(tmp_path):
    legacy = tmp_path / "fill_redmine.db"
    target = tmp_path / "work_assistant.db"
    legacy.write_bytes(b"old-data")

    result = migrate_legacy_database(target, legacy, log=lambda message: None)

    assert result is True
    assert target.read_bytes() == b"old-data"
    assert not legacy.exists()


def test_migrate_legacy_database_keeps_existing_target(tmp_path):
    legacy = tmp_path / "fill_redmine.db"
    target = tmp_path / "work_assistant.db"
    legacy.write_bytes(b"old")
    target.write_bytes(b"new")

    result = migrate_legacy_database(target, legacy, log=lambda message: None)

    assert result is False
    assert target.read_bytes() == b"new"
    assert legacy.read_bytes() == b"old"


def test_migrate_default_skips_when_env_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv("WORK_ASSISTANT_DB", str(tmp_path / "custom.db"))

    assert migrate_default_legacy_database(log=lambda message: None) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_repository.py tests/test_database.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'configs.project_config'`.

- [ ] **Step 3: Add ProjectConfig**

```python
# configs/project_config.py
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    git_author_email: str = ""
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    trackers: dict[str, dict[str, Any]] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    db_id: int | None = None

    def tracker(self, kind: str) -> dict[str, Any]:
        return self.trackers.get(kind, {})
```

- [ ] **Step 4: Extend storage/database.py**

Replace the module with:

```python
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
```

- [ ] **Step 5: Add ProjectRepository**

```python
# storage/project_repository.py
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
```

- [ ] **Step 6: Run tests and full suite**

Run: `pytest tests/test_project_repository.py tests/test_database.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS (все старые тесты тоже).

- [ ] **Step 7: Commit**

```bash
git add configs/project_config.py storage/database.py storage/project_repository.py tests/test_project_repository.py tests/test_database.py
git commit -m "feat: add project storage and repository"
```

---

### Task 2: Миграция юзеров в проекты

**Files:**
- Modify: `storage/migration.py`
- Create: `tests/test_project_migration.py`

**Interfaces:**
- Consumes: `ProjectRepository`, `UserRepository`, `ProjectConfig`.
- Produces: `migrate_users_to_projects(project_repo, user_repo, log=print) -> int`.

- [ ] **Step 1: Write failing migration tests**

```python
# tests/test_project_migration.py
from configs.user_config import UserConfig
from storage.migration import migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


def make_user(**overrides) -> UserConfig:
    data = dict(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="youtrack",
        youtrack_access_token="token",
        exclude_dates=["2026-10-05"],
    )
    data.update(overrides)
    return UserConfig(**data)


def make_repos(tmp_path):
    db_path = tmp_path / "test.db"
    return (
        ProjectRepository(db_path=db_path),
        UserRepository(db_path=db_path),
    )


def test_migrates_user_fields_to_project(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user())

    count = migrate_users_to_projects(
        project_repo, user_repo, log=lambda message: None
    )

    assert count == 1
    project = project_repo.list_projects()[0]
    assert project.name == "Олег"
    assert project.exclude_dates == ["2026-10-05"]
    assert project.trackers["redmine"] == {
        "api_key": "key",
        "user_id": 16,
        "activity_id": 9,
        "issue_id": 2682,
        "comment": "development",
    }
    assert project.trackers["youtrack"] == {"access_token": "token"}
    assert project_repo.get_meta("legacy_users_migrated") == "1"


def test_manual_user_gets_only_redmine_tracker(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user(driver="manual", youtrack_access_token=""))

    migrate_users_to_projects(project_repo, user_repo, log=lambda message: None)

    project = project_repo.list_projects()[0]
    assert "redmine" in project.trackers
    assert "youtrack" not in project.trackers


def test_migration_is_idempotent(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_user(make_user())

    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 1
    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 0
    assert len(project_repo.list_projects()) == 1


def test_duplicate_names_get_suffix(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)
    user_repo.add_users([make_user(), make_user(user_id=17)])

    migrate_users_to_projects(project_repo, user_repo, log=lambda message: None)

    assert [p.name for p in project_repo.list_projects()] == ["Олег", "Олег (2)"]


def test_no_users_does_not_mark_migration(tmp_path):
    project_repo, user_repo = make_repos(tmp_path)

    assert migrate_users_to_projects(project_repo, user_repo, log=print) == 0
    assert project_repo.get_meta("legacy_users_migrated") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_migration.py -q`
Expected: FAIL with `ImportError: cannot import name 'migrate_users_to_projects'`.

- [ ] **Step 3: Implement migration**

Append to `storage/migration.py`:

```python
from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository

USERS_MIGRATED_KEY = "legacy_users_migrated"


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
```

Убедитесь, что в `storage/migration.py` импорты `Callable`, `ProjectRepository`, `UserRepository`, `ProjectConfig` не дублируются.

- [ ] **Step 4: Run tests and full suite**

Run: `pytest tests/test_project_migration.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add storage/migration.py tests/test_project_migration.py
git commit -m "feat: migrate legacy users to projects"
```

---

### Task 3: Базовый трекер и реестр

**Files:**
- Create: `dto/worklog_dto.py`
- Create: `trackers/__init__.py`
- Create: `trackers/base.py`
- Create: `trackers/registry.py`
- Create: `tests/test_tracker_registry.py`

**Interfaces:**
- Consumes: `ProjectConfig`.
- Produces:
  - `TrackerField(key, label, kind="text", required=True, placeholder="")`
  - `WorklogDTO(date, hours, description="", issue="", source="")`
  - `BaseTracker(config)`
  - `BaseTracker.is_configured() -> bool`
  - `BaseTracker.validate_config(config) -> list[str]` (classmethod)
  - `BaseTracker.get_worklogs(start: date, end: date) -> list[WorklogDTO]`
  - `register_tracker(cls)`, `all_trackers()`, `get_tracker_class(kind)`, `build_tracker(kind, config)`, `configured_trackers(project)`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_tracker_registry.py
from datetime import date

import pytest

from configs.project_config import ProjectConfig
from trackers.base import BaseTracker, TrackerField
from trackers.registry import (
    all_trackers,
    build_tracker,
    configured_trackers,
    get_tracker_class,
    register_tracker,
)


class FakeTracker(BaseTracker):
    kind = "fake_test"
    label = "Fake"
    fields = (
        TrackerField("token", "Token", kind="secret"),
        TrackerField("user_id", "User ID", kind="int"),
    )

    def get_worklogs(self, start: date, end: date):
        return []


def test_register_and_build():
    register_tracker(FakeTracker)

    assert get_tracker_class("fake_test") is FakeTracker
    assert FakeTracker in all_trackers()
    tracker = build_tracker("fake_test", {"token": "t", "user_id": 1})
    assert isinstance(tracker, FakeTracker)


def test_duplicate_registration_raises():
    register_tracker(FakeTracker)

    with pytest.raises(ValueError):
        register_tracker(FakeTracker)


def test_is_configured_requires_all_required_fields():
    tracker = FakeTracker({"token": "t"})

    assert tracker.is_configured() is False


def test_empty_config_is_not_configured():
    assert FakeTracker({}).is_configured() is False


def test_validate_config_allows_empty_section():
    assert FakeTracker.validate_config({}) == []


def test_validate_config_reports_partial_fields():
    errors = FakeTracker.validate_config({"token": "t"})

    assert len(errors) == 1
    assert "Fake" in errors[0]
    assert "User ID" in errors[0]


def test_validate_config_reports_bad_int():
    errors = FakeTracker.validate_config({"token": "t", "user_id": "abc"})

    assert any("User ID" in error for error in errors)


def test_configured_trackers_filters_unconfigured():
    project = ProjectConfig(
        name="P",
        trackers={"fake_test": {"token": "t", "user_id": 1}},
    )

    trackers = configured_trackers(project)

    assert [type(tracker) for tracker in trackers] == [FakeTracker]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tracker_registry.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'trackers'`.

- [ ] **Step 3: Implement DTO and base tracker**

```python
# dto/worklog_dto.py
from dataclasses import dataclass


@dataclass
class WorklogDTO:
    date: str
    hours: float
    description: str = ""
    issue: str = ""
    source: str = ""
```

```python
# trackers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from dto.worklog_dto import WorklogDTO


@dataclass(frozen=True)
class TrackerField:
    key: str
    label: str
    kind: str = "text"
    required: bool = True
    placeholder: str = ""


class BaseTracker(ABC):
    kind: str = ""
    label: str = ""
    fields: tuple[TrackerField, ...] = ()
    can_read: bool = True
    can_write: bool = False

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    def is_configured(self) -> bool:
        required = [field for field in self.fields if field.required]
        return bool(required) and all(
            self.config.get(field.key) not in (None, "")
            for field in required
        )

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        required = [field for field in cls.fields if field.required]
        filled = [
            field
            for field in required
            if config.get(field.key) not in (None, "")
        ]
        if not filled:
            return []

        errors: list[str] = []
        missing = [field.label for field in required if field not in filled]
        if missing:
            errors.append(
                f"{cls.label}: заполните {', '.join(missing)}"
            )
            return errors

        for field in required:
            if field.kind == "int":
                try:
                    value = int(config[field.key])
                except (TypeError, ValueError):
                    errors.append(f"{cls.label}: {field.label} должно быть целым числом")
                    continue
                if value <= 0:
                    errors.append(f"{cls.label}: {field.label} должно быть больше нуля")
        return errors

    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        raise NotImplementedError

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError(
            f"Трекер {self.label} не поддерживает запись часов"
        )
```

- [ ] **Step 4: Implement registry**

```python
# trackers/registry.py
from configs.project_config import ProjectConfig
from trackers.base import BaseTracker

_REGISTRY: dict[str, type[BaseTracker]] = {}


def register_tracker(cls: type[BaseTracker]) -> type[BaseTracker]:
    if not issubclass(cls, BaseTracker):
        raise TypeError("register_tracker ожидает класс BaseTracker")
    if not cls.kind:
        raise ValueError("У трекера не задан kind")
    if cls.kind in _REGISTRY:
        raise ValueError(f"Трекер {cls.kind} уже зарегистрирован")
    _REGISTRY[cls.kind] = cls
    return cls


def all_trackers() -> list[type[BaseTracker]]:
    return list(_REGISTRY.values())


def get_tracker_class(kind: str) -> type[BaseTracker] | None:
    return _REGISTRY.get(kind)


def build_tracker(kind: str, config: dict) -> BaseTracker | None:
    cls = get_tracker_class(kind)
    return cls(config) if cls is not None else None


def configured_trackers(project: ProjectConfig) -> list[BaseTracker]:
    result: list[BaseTracker] = []
    for cls in all_trackers():
        tracker = cls(project.trackers.get(cls.kind, {}))
        if tracker.is_configured():
            result.append(tracker)
    return result
```

```python
# trackers/__init__.py
from trackers.base import BaseTracker, TrackerField
from trackers.registry import (
    all_trackers,
    build_tracker,
    configured_trackers,
    get_tracker_class,
    register_tracker,
)

__all__ = [
    "BaseTracker",
    "TrackerField",
    "all_trackers",
    "build_tracker",
    "configured_trackers",
    "get_tracker_class",
    "register_tracker",
]
```

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_tracker_registry.py -q`
Expected: PASS.

```bash
git add dto/worklog_dto.py trackers tests/test_tracker_registry.py
git commit -m "feat: add tracker abstraction and registry"
```

---

### Task 4: RedmineTracker и чтение time entries

**Files:**
- Modify: `clients/redmine_client.py`
- Create: `trackers/redmine.py`
- Modify: `trackers/__init__.py`
- Create: `tests/test_redmine_tracker.py`

**Interfaces:**
- Consumes: `BaseTracker`, `TrackerField`, `WorklogDTO`.
- Produces:
  - `RedmineClient.PAGE_SIZE = 100`
  - `RedmineClient.get_time_entries(user_id, start: date, end: date) -> list[dict]`
  - `RedmineTracker` с `kind="redmine"`, `can_write=True`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_redmine_tracker.py
from datetime import date
from unittest.mock import MagicMock, patch

from clients.redmine_client import RedmineClient
from trackers.redmine import RedmineTracker


def test_get_time_entries_paginates(monkeypatch):
    monkeypatch.setattr(RedmineClient, "PAGE_SIZE", 2)
    page_one = MagicMock()
    page_one.json.return_value = {
        "time_entries": [
            {"spent_on": "2026-10-01", "hours": 2},
            {"spent_on": "2026-10-02", "hours": 3},
        ],
        "total_count": 3,
    }
    page_one.raise_for_status = MagicMock()
    page_two = MagicMock()
    page_two.json.return_value = {
        "time_entries": [{"spent_on": "2026-10-03", "hours": 4}],
        "total_count": 3,
    }
    page_two.raise_for_status = MagicMock()

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.requests.get",
        side_effect=[page_one, page_two],
    ) as mock_get:
        entries = RedmineClient("key").get_time_entries(
            user_id=16, start=date(2026, 10, 1), end=date(2026, 10, 3)
        )

    assert [entry["hours"] for entry in entries] == [2, 3, 4]
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["offset"] == 2


def test_tracker_maps_worklogs():
    tracker = RedmineTracker(
        {
            "api_key": "key",
            "user_id": 16,
            "activity_id": 9,
            "issue_id": 2682,
            "comment": "dev",
        }
    )
    with patch.object(
        RedmineClient,
        "get_time_entries",
        return_value=[
            {
                "spent_on": "2026-10-01",
                "hours": 3.5,
                "comments": "fix",
                "issue": {"id": 2682},
            }
        ],
    ):
        worklogs = tracker.get_worklogs(date(2026, 10, 1), date(2026, 10, 2))

    assert len(worklogs) == 1
    assert worklogs[0].hours == 3.5
    assert worklogs[0].description == "fix"
    assert worklogs[0].issue == "2682"
    assert worklogs[0].source == "redmine"


def test_tracker_is_configured():
    assert RedmineTracker({"api_key": "key", "user_id": 1, "activity_id": 2, "issue_id": 3}).is_configured()
    assert not RedmineTracker({}).is_configured()


def test_tracker_is_registered():
    from trackers.registry import get_tracker_class

    assert get_tracker_class("redmine") is RedmineTracker
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_redmine_tracker.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'trackers.redmine'`.

- [ ] **Step 3: Add Redmine time entries**

Добавьте в `clients/redmine_client.py` импорт `from datetime import date` и метод:

```python
    PAGE_SIZE = 100

    def get_time_entries(
        self, user_id: int, start: date, end: date
    ) -> list[dict]:
        url = f"{self.base_url}/time_entries.json"
        headers = {"X-Redmine-API-Key": self.api_key}
        entries: list[dict] = []
        offset = 0

        while True:
            params = {
                "user_id": user_id,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "limit": self.PAGE_SIZE,
                "offset": offset,
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("time_entries", [])
            entries.extend(batch)
            total = int(payload.get("total_count", len(entries)))
            if not batch or len(batch) < self.PAGE_SIZE or len(entries) >= total:
                break
            offset += self.PAGE_SIZE

        return entries
```

- [ ] **Step 4: Add RedmineTracker**

```python
# trackers/redmine.py
from datetime import date

from clients.redmine_client import RedmineClient
from dto.worklog_dto import WorklogDTO
from trackers.base import BaseTracker, TrackerField
from trackers.registry import register_tracker


@register_tracker
class RedmineTracker(BaseTracker):
    kind = "redmine"
    label = "Redmine"
    can_write = True
    fields = (
        TrackerField("api_key", "API key", kind="secret"),
        TrackerField("user_id", "user_id", kind="int"),
        TrackerField("activity_id", "activity_id", kind="int"),
        TrackerField("issue_id", "issue_id", kind="int"),
        TrackerField("comment", "Комментарий", kind="textarea", required=False),
    )

    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        client = RedmineClient(api_key=self.config["api_key"])
        entries = client.get_time_entries(
            user_id=int(self.config["user_id"]),
            start=start,
            end=end,
        )
        result: list[WorklogDTO] = []
        for entry in entries:
            issue = entry.get("issue") or {}
            result.append(
                WorklogDTO(
                    date=entry["spent_on"],
                    hours=float(entry.get("hours", 0)),
                    description=entry.get("comments", ""),
                    issue=str(issue.get("id", "")),
                    source=self.kind,
                )
            )
        return result
```

- [ ] **Step 5: Register tracker**

Добавьте в `trackers/__init__.py` после импортов registry:

```python
from trackers.redmine import RedmineTracker  # noqa: E402,F401
```

- [ ] **Step 6: Run tests and commit**

Run: `pytest tests/test_redmine_tracker.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

```bash
git add clients/redmine_client.py trackers/redmine.py trackers/__init__.py tests/test_redmine_tracker.py
git commit -m "feat: read Redmine time entries via tracker"
```

---

### Task 5: YoutrackTracker и пагинация work items

**Files:**
- Modify: `clients/youtrack_client.py`
- Create: `trackers/youtrack.py`
- Modify: `trackers/__init__.py`
- Create: `tests/test_youtrack_tracker.py`

**Interfaces:**
- Consumes: `BaseTracker`, `TrackerField`, `WorklogDTO`.
- Produces:
  - `YoutrackClient.PAGE_SIZE = 100`
  - `YoutrackClient.get_work_items(start: datetime, end: datetime) -> list[dict]` с пагинацией.
  - `YoutrackTracker` с `kind="youtrack"`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_youtrack_tracker.py
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from clients.youtrack_client import YoutrackClient
from trackers.youtrack import YoutrackTracker


def test_get_work_items_paginates(monkeypatch):
    monkeypatch.setattr(YoutrackClient, "PAGE_SIZE", 2)
    page_one = MagicMock()
    page_one.json.return_value = [{"date": 1}, {"date": 2}]
    page_one.raise_for_status = MagicMock()
    page_two = MagicMock()
    page_two.json.return_value = [{"date": 3}]
    page_two.raise_for_status = MagicMock()

    with patch(
        "clients.youtrack_client.Config.get_youtrack_base_url",
        return_value="http://youtrack",
    ), patch(
        "clients.youtrack_client.requests.get",
        side_effect=[page_one, page_two],
    ) as mock_get:
        items = YoutrackClient("token").get_work_items(
            datetime(2026, 10, 1), datetime(2026, 10, 31)
        )

    assert len(items) == 3
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[1].kwargs["params"]["$skip"] == 2


def test_tracker_aggregates_minutes_by_day():
    tracker = YoutrackTracker({"access_token": "token"})
    with patch.object(
        YoutrackClient,
        "get_work_items",
        return_value=[
            {"date": 1790812800000, "duration": {"minutes": 120}, "text": "a"},
            {"date": 1790812800000, "duration": {"minutes": 240}, "text": "b"},
            {"date": 1790899200000, "duration": {"minutes": 480}, "text": "c"},
        ],
    ):
        worklogs = tracker.get_worklogs(date(2026, 10, 1), date(2026, 10, 2))

    assert [(w.date, w.hours) for w in worklogs] == [
        ("2026-10-01", 6.0),
        ("2026-10-02", 8.0),
    ]
    assert worklogs[0].source == "youtrack"


def test_tracker_is_configured():
    assert YoutrackTracker({"access_token": "token"}).is_configured()
    assert not YoutrackTracker({}).is_configured()


def test_tracker_is_registered():
    from trackers.registry import get_tracker_class

    assert get_tracker_class("youtrack") is YoutrackTracker
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_youtrack_tracker.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'trackers.youtrack'`.

- [ ] **Step 3: Add pagination to YoutrackClient**

Replace `get_work_items` in `clients/youtrack_client.py`:

```python
    PAGE_SIZE = 100

    def get_work_items(self, start_date: datetime, end_date: datetime) -> list[dict]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/api/workItems"
        items: list[dict] = []
        skip = 0

        while True:
            params = {
                "fields": "id,date,duration(minutes),text,issue(idReadable)",
                "start": int(start_date.timestamp() * 1000),
                "end": int(end_date.timestamp() * 1000),
                "$top": self.PAGE_SIZE,
                "$skip": skip,
                "author": "me",
            }
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            batch = response.json()
            items.extend(batch)
            if len(batch) < self.PAGE_SIZE:
                break
            skip += self.PAGE_SIZE

        return items
```

- [ ] **Step 4: Add YoutrackTracker**

```python
# trackers/youtrack.py
from datetime import date, datetime

from clients.youtrack_client import YoutrackClient
from dto.worklog_dto import WorklogDTO
from trackers.base import BaseTracker, TrackerField
from trackers.registry import register_tracker


@register_tracker
class YoutrackTracker(BaseTracker):
    kind = "youtrack"
    label = "YouTrack"
    fields = (TrackerField("access_token", "Access token", kind="secret"),)

    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        client = YoutrackClient(access_token=self.config["access_token"])
        items = client.get_work_items(
            start_date=datetime.combine(start, datetime.min.time()),
            end_date=datetime.combine(end, datetime.max.time()),
        )
        by_date: dict[str, float] = {}
        for item in items:
            item_date = datetime.fromtimestamp(item["date"] / 1000).date().isoformat()
            minutes = float((item.get("duration") or {}).get("minutes", 0))
            by_date[item_date] = by_date.get(item_date, 0) + minutes / 60

        return [
            WorklogDTO(date=item_date, hours=hours, source=self.kind)
            for item_date, hours in sorted(by_date.items())
        ]
```

- [ ] **Step 5: Register tracker and run tests**

Добавьте в `trackers/__init__.py`:

```python
from trackers.youtrack import YoutrackTracker  # noqa: E402,F401
```

Run: `pytest tests/test_youtrack_tracker.py tests/test_youtrack_import.py -q`
Expected: PASS (старые тесты импорта пока используют UserConfig и должны остаться зелёными).

- [ ] **Step 6: Commit**

```bash
git add clients/youtrack_client.py trackers/youtrack.py trackers/__init__.py tests/test_youtrack_tracker.py
git commit -m "feat: read YouTrack work items via tracker"
```

---

### Task 6: Git client

**Files:**
- Create: `dto/git_commit_dto.py`
- Create: `clients/git_client.py`
- Create: `tests/test_git_client.py`

**Interfaces:**
- Consumes: ничего.
- Produces:
  - `GitCommitDTO(hash, author_name, author_email, date, subject, body)`
  - `GitError(RuntimeError)`
  - `GitClient(repo_path)`
  - `GitClient.validate() -> None`
  - `GitClient.get_config_email() -> str`
  - `GitClient.list_commits(email, start: date, end: date) -> list[GitCommitDTO]`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_git_client.py
import os
import subprocess
from datetime import date

import pytest

from clients.git_client import GitClient, GitError


def run_git(repo, *args, env=None):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.name", "Oleg")
    run_git(path, "config", "user.email", "oleg@example.com")
    return path


def commit(repo, message, author_date, email="oleg@example.com"):
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = author_date
    env["GIT_COMMITTER_DATE"] = author_date
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_COMMITTER_EMAIL"] = email
    (repo / "file.txt").write_text(message)
    run_git(repo, "add", "file.txt")
    run_git(repo, "commit", "-m", message, env=env)


def test_lists_commits_from_all_branches(repo):
    commit(repo, "main commit", "2026-10-01T10:00:00+00:00")
    run_git(repo, "checkout", "-b", "feature")
    commit(repo, "feature commit", "2026-10-02T10:00:00+00:00")
    run_git(repo, "checkout", "main")

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert {commit.subject for commit in commits} == {
        "main commit",
        "feature commit",
    }


def test_filters_by_author_email(repo):
    commit(repo, "mine", "2026-10-01T10:00:00+00:00")
    commit(
        repo,
        "theirs",
        "2026-10-02T10:00:00+00:00",
        email="other@example.com",
    )

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["mine"]


def test_filters_by_period(repo):
    commit(repo, "old", "2026-09-01T10:00:00+00:00")
    commit(repo, "inside", "2026-10-02T10:00:00+00:00")

    commits = GitClient(repo).list_commits(
        "oleg@example.com", date(2026, 10, 1), date(2026, 10, 5)
    )

    assert [commit.subject for commit in commits] == ["inside"]


def test_get_config_email(repo):
    assert GitClient(repo).get_config_email() == "oleg@example.com"


def test_empty_email_raises(repo):
    with pytest.raises(GitError, match="email"):
        GitClient(repo).list_commits("", date(2026, 10, 1), date(2026, 10, 2))


def test_not_a_repository_raises(tmp_path):
    with pytest.raises(GitError, match="git"):
        GitClient(tmp_path).validate()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_git_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clients.git_client'`.

- [ ] **Step 3: Implement DTO and client**

```python
# dto/git_commit_dto.py
from dataclasses import dataclass


@dataclass
class GitCommitDTO:
    hash: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str = ""
```

```python
# clients/git_client.py
import subprocess
from datetime import date
from pathlib import Path

from dto.git_commit_dto import GitCommitDTO

FIELD_SEPARATOR = "\x1f"
RECORD_SEPARATOR = "\x1e"


class GitError(RuntimeError):
    pass


class GitClient:
    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).expanduser()

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path), *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise GitError(message or "git command failed")
        return result.stdout

    def validate(self) -> None:
        if not self.repo_path.exists():
            raise GitError(f"Путь к репозиторию не найден: {self.repo_path}")
        try:
            inside = self._run("rev-parse", "--is-inside-work-tree").strip()
        except GitError as exc:
            raise GitError("Это не git-репозиторий") from exc
        if inside != "true":
            raise GitError("Это не git-репозиторий")

    def get_config_email(self) -> str:
        self.validate()
        return self._run("config", "user.email").strip()

    def list_commits(
        self, email: str, start: date, end: date
    ) -> list[GitCommitDTO]:
        email = email.strip()
        if not email:
            raise GitError("Не задан email автора коммитов")
        self.validate()

        output = self._run(
            "log",
            "--all",
            f"--author={email}",
            f"--since={start.isoformat()}T00:00:00",
            f"--until={end.isoformat()}T23:59:59",
            "--date=iso-strict",
            "--pretty=format:"
            f"%H{FIELD_SEPARATOR}%an{FIELD_SEPARATOR}%ae{FIELD_SEPARATOR}"
            f"%ad{FIELD_SEPARATOR}%s{FIELD_SEPARATOR}%b{RECORD_SEPARATOR}",
        )

        commits: dict[str, GitCommitDTO] = {}
        for raw_record in output.split(RECORD_SEPARATOR):
            record = raw_record.strip("\n")
            if not record:
                continue
            parts = record.split(FIELD_SEPARATOR, maxsplit=5)
            if len(parts) != 6:
                continue
            commit_hash, author_name, author_email, authored_at, subject, body = parts
            if author_email.strip().lower() != email.lower():
                continue
            commits[commit_hash] = GitCommitDTO(
                hash=commit_hash,
                author_name=author_name,
                author_email=author_email,
                date=authored_at,
                subject=subject,
                body=body.strip(),
            )

        return sorted(commits.values(), key=lambda item: item.date, reverse=True)
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_git_client.py -q`
Expected: PASS.

```bash
git add dto/git_commit_dto.py clients/git_client.py tests/test_git_client.py
git commit -m "feat: read commits from all git branches"
```

---

### Task 7: AI client

**Files:**
- Create: `clients/ai_client.py`
- Create: `tests/test_ai_client.py`

**Interfaces:**
- Consumes: `ProjectConfig`.
- Produces:
  - `AiError(RuntimeError)`
  - `AiConfig(base_url, model, api_key)`
  - `resolve_ai_config(project) -> AiConfig`
  - `AiClient(config)`
  - `AiClient.complete_json(system_prompt, user_prompt) -> dict`
  - `parse_json_object(text) -> dict`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai_client.py
from unittest.mock import MagicMock, patch

import pytest

from clients.ai_client import (
    AiClient,
    AiConfig,
    AiError,
    parse_json_object,
    resolve_ai_config,
)
from configs.project_config import ProjectConfig


def test_project_settings_override_env(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    project = ProjectConfig(
        name="P",
        ai={
            "base_url": "https://project.example/v1",
            "model": "project-model",
            "api_key": "project-key",
        },
    )

    config = resolve_ai_config(project)

    assert config == AiConfig(
        base_url="https://project.example/v1",
        model="project-model",
        api_key="project-key",
    )


def test_env_fallback_and_default_base_url(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    config = resolve_ai_config(ProjectConfig(name="P"))

    assert config.base_url == "https://api.openai.com/v1"
    assert config.model == "env-model"
    assert config.api_key == "env-key"


def test_missing_model_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    with pytest.raises(AiError, match="модель"):
        resolve_ai_config(ProjectConfig(name="P"))


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "model")

    with pytest.raises(AiError, match="ключ"):
        resolve_ai_config(ProjectConfig(name="P"))


def test_parse_json_with_markdown_fence():
    payload = parse_json_object('```json\n{"summary": "ok"}\n```')

    assert payload == {"summary": "ok"}


def test_complete_json_sends_request():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": '{"summary": "ok"}'}}]
    }

    with patch("clients.ai_client.requests.post", return_value=response) as post:
        result = client.complete_json("system", "user")

    assert result == {"summary": "ok"}
    body = post.call_args.kwargs["json"]
    assert body["model"] == "model"
    assert body["messages"][0]["content"] == "system"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer key"


def test_http_error_raises():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 500
    response.text = "boom"

    with patch("clients.ai_client.requests.post", return_value=response):
        with pytest.raises(AiError, match="500"):
            client.complete_json("system", "user")


def test_invalid_json_raises():
    client = AiClient(AiConfig("https://api.example/v1", "model", "key"))
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": "not-json"}}]
    }

    with patch("clients.ai_client.requests.post", return_value=response):
        with pytest.raises(AiError, match="JSON"):
            client.complete_json("system", "user")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ai_client.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'clients.ai_client'`.

- [ ] **Step 3: Implement AiClient**

```python
# clients/ai_client.py
import json
import os
from dataclasses import dataclass

import requests

from configs.project_config import ProjectConfig


class AiError(RuntimeError):
    pass


@dataclass(frozen=True)
class AiConfig:
    base_url: str
    model: str
    api_key: str


def resolve_ai_config(project: ProjectConfig) -> AiConfig:
    base_url = str(
        project.ai.get("base_url")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    model = str(project.ai.get("model") or os.getenv("OPENAI_MODEL") or "")
    api_key = str(
        project.ai.get("api_key") or os.getenv("OPENAI_API_KEY") or ""
    )
    if not model:
        raise AiError("Не задана модель ИИ (model)")
    if not api_key:
        raise AiError("Не задан API-ключ ИИ (api_key)")
    return AiConfig(base_url=base_url, model=model, api_key=api_key)


def parse_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise AiError("ИИ вернул ответ без JSON-объекта")
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AiError(f"ИИ вернул невалидный JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiError("ИИ вернул JSON не-объект")
    return parsed


class AiClient:
    def __init__(self, config: AiConfig):
        self.config = config

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            },
            timeout=120,
        )
        if not 200 <= response.status_code < 300:
            raise AiError(
                f"HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiError(f"Неожиданный ответ ИИ: {exc}") from exc
        return parse_json_object(content)
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_ai_client.py -q`
Expected: PASS.

```bash
git add clients/ai_client.py tests/test_ai_client.py
git commit -m "feat: add OpenAI-compatible AI client"
```

---

### Task 8: CommitPlanService — дефицит, промпт и валидация

**Files:**
- Create: `dto/commit_plan_dto.py`
- Create: `services/commit_plan_service.py`
- Create: `tests/test_commit_plan_service.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `GitCommitDTO`, `BaseTracker`, `AiClient`.
- Produces:
  - `PlanError(RuntimeError)`
  - `DayPlanDTO(date, existing_hours, deficit_hours, planned_hours, comment, commit_hashes, confidence)`
  - `CommitPlanDTO(summary, days, raw_response="")`
  - `CommitPlanService(ai_client, tracker_builder=build_tracker, log=print)`
  - `CommitPlanService.generate(project, start, end, selected_kinds, commits) -> CommitPlanDTO`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_commit_plan_service.py
from datetime import date

import pytest

from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO
from dto.git_commit_dto import GitCommitDTO
from dto.worklog_dto import WorklogDTO
from services.commit_plan_service import CommitPlanService, PlanError
from trackers.base import BaseTracker, TrackerField


class FakeTracker(BaseTracker):
    kind = "fake_plan"
    label = "Fake"
    fields = (TrackerField("token", "Token"),)

    def get_worklogs(self, start, end):
        return [
            WorklogDTO(date="2026-10-01", hours=3),
            WorklogDTO(date="2026-10-02", hours=8),
        ]


class BrokenTracker(BaseTracker):
    kind = "broken_plan"
    label = "Broken"
    fields = (TrackerField("token", "Token"),)

    def get_worklogs(self, start, end):
        raise RuntimeError("tracker down")


class FakeAi:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return self.payload


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        workday_hours=8.0,
        exclude_dates=[],
        trackers={"fake_plan": {"token": "t"}},
    )
    data.update(overrides)
    return ProjectConfig(**data)


def make_commits() -> list[GitCommitDTO]:
    return [
        GitCommitDTO(
            hash="aaa111",
            author_name="Oleg",
            author_email="oleg@example.com",
            date="2026-10-01T10:00:00+00:00",
            subject="Add import",
        ),
        GitCommitDTO(
            hash="bbb222",
            author_name="Oleg",
            author_email="oleg@example.com",
            date="2026-10-02T10:00:00+00:00",
            subject="Fix tests",
        ),
    ]


def make_service(payload, **overrides) -> CommitPlanService:
    service = CommitPlanService(ai_client=FakeAi(payload), log=lambda message: None)
    service.tracker_builder = lambda kind, config: FakeTracker(config)
    return service


def test_generates_plan_and_caps_hours():
    payload = {
        "summary": "ok",
        "days": [
            {
                "date": "2026-10-01",
                "hours": 4,
                "comment": "Импорт",
                "commit_hashes": ["aaa111", "unknown"],
                "confidence": "high",
            },
            {
                "date": "2026-10-02",
                "hours": 8,
                "comment": "Тесты",
                "commit_hashes": ["bbb222"],
                "confidence": "medium",
            },
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 2),
        ["fake_plan"],
        make_commits(),
    )

    assert isinstance(plan, CommitPlanDTO)
    assert plan.summary == "ok"
    first = plan.days[0]
    assert first.date == "2026-10-01"
    assert first.existing_hours == 3
    assert first.deficit_hours == 5
    assert first.planned_hours == 4
    assert first.commit_hashes == ["aaa111"]
    second = plan.days[1]
    assert second.existing_hours == 8
    assert second.deficit_hours == 0
    assert second.planned_hours == 0


def test_weekend_and_excluded_days_have_zero_target():
    payload = {"summary": "ok", "days": []}
    service = make_service(payload)

    plan = service.generate(
        make_project(exclude_dates=["2026-10-03"]),
        date(2026, 10, 3),
        date(2026, 10, 4),
        ["fake_plan"],
        [],
    )

    assert [day.deficit_hours for day in plan.days] == [0, 0]


def test_snaps_hours_to_half_and_removes_unknown_hashes():
    payload = {
        "summary": "ok",
        "days": [
            {
                "date": "2026-10-01",
                "hours": 1.3,
                "comment": "x",
                "commit_hashes": ["nope"],
                "confidence": "weird",
            }
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 1),
        ["fake_plan"],
        make_commits(),
    )

    assert plan.days[0].planned_hours == 1.5
    assert plan.days[0].commit_hashes == []
    assert plan.days[0].confidence == "low"


def test_ignores_dates_outside_period():
    payload = {
        "summary": "ok",
        "days": [
            {"date": "2026-09-01", "hours": 4, "comment": "x"},
        ],
    }
    service = make_service(payload)

    plan = service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 1),
        ["fake_plan"],
        [],
    )

    assert all(day.date != "2026-09-01" for day in plan.days)
    assert plan.days[0].planned_hours == 0


def test_requires_selected_tracker():
    service = make_service({"summary": "ok", "days": []})

    with pytest.raises(PlanError, match="трекер"):
        service.generate(
            make_project(), date(2026, 10, 1), date(2026, 10, 1), [], []
        )


def test_tracker_failure_aborts():
    service = make_service({"summary": "ok", "days": []})
    service.tracker_builder = lambda kind, config: BrokenTracker(config)

    with pytest.raises(PlanError, match="Broken"):
        service.generate(
            make_project(trackers={"broken_plan": {"token": "t"}}),
            date(2026, 10, 1),
            date(2026, 10, 1),
            ["broken_plan"],
            [],
        )


def test_prompt_contains_commits_and_deficit():
    ai = FakeAi({"summary": "ok", "days": []})
    service = CommitPlanService(ai_client=ai, log=lambda message: None)
    service.tracker_builder = lambda kind, config: FakeTracker(config)

    service.generate(
        make_project(),
        date(2026, 10, 1),
        date(2026, 10, 2),
        ["fake_plan"],
        make_commits(),
    )

    _, user_prompt = ai.calls[0]
    assert "Проект" in user_prompt
    assert "Add import" in user_prompt
    assert '"deficit_hours": 5.0' in user_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_commit_plan_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.commit_plan_service'`.

- [ ] **Step 3: Implement DTOs and service**

```python
# dto/commit_plan_dto.py
from dataclasses import dataclass, field


@dataclass
class DayPlanDTO:
    date: str
    existing_hours: float
    deficit_hours: float
    planned_hours: float
    comment: str = ""
    commit_hashes: list[str] = field(default_factory=list)
    confidence: str = "low"


@dataclass
class CommitPlanDTO:
    summary: str
    days: list[DayPlanDTO]
    raw_response: str = ""
```

```python
# services/commit_plan_service.py
import json
from collections.abc import Callable
from datetime import date, timedelta

from clients.ai_client import AiClient
from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from dto.git_commit_dto import GitCommitDTO
from trackers.base import BaseTracker
from trackers.registry import build_tracker

SYSTEM_PROMPT = """Ты — ассистент по учёту рабочего времени.
Верни ТОЛЬКО JSON-объект без markdown:
{"summary": "краткий итог", "days": [{"date": "YYYY-MM-DD", "hours": 0.0,
"comment": "краткое описание работы", "commit_hashes": ["hash"],
"confidence": "high|medium|low"}]}
Правила:
- используй только переданные коммиты и их хеши;
- не придумывай работу, если коммитов за день нет — верни 0 часов;
- комментарии пиши по-русски, кратко и по делу;
- часы не больше deficit_hours и кратны 0.5;
- предлагай часы только на дни с положительным deficit_hours.
"""


class PlanError(RuntimeError):
    pass


class CommitPlanService:
    def __init__(
        self,
        ai_client: AiClient,
        tracker_builder: Callable[[str, dict], BaseTracker | None] = build_tracker,
        log: Callable[[str], None] = print,
    ) -> None:
        self.ai_client = ai_client
        self.tracker_builder = tracker_builder
        self.log = log

    def generate(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        selected_kinds: list[str],
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        if start > end:
            raise PlanError("Начало периода позже конца")
        if not selected_kinds:
            raise PlanError("Выберите хотя бы один трекер")

        existing = self._collect_existing(project, start, end, selected_kinds)
        days = self._build_days(project, start, end, existing)
        payload = {
            "project": project.name,
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "workday_hours": project.workday_hours,
            "days": [
                {
                    "date": day.date,
                    "target_hours": (
                        project.workday_hours
                        if date.fromisoformat(day.date).weekday() < 5
                        and day.date not in project.exclude_dates
                        else 0.0
                    ),
                    "existing_hours": day.existing_hours,
                    "deficit_hours": day.deficit_hours,
                    "commits": [
                        {
                            "hash": commit.hash,
                            "subject": commit.subject,
                            "body": commit.body[:1000],
                        }
                        for commit in commits
                        if commit.date[:10] == day.date
                    ],
                }
                for day in days
            ],
        }
        raw = self.ai_client.complete_json(
            SYSTEM_PROMPT,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        return self._apply_ai_response(days, raw, commits)

    def _collect_existing(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        selected_kinds: list[str],
    ) -> dict[str, float]:
        existing: dict[str, float] = {}
        for kind in selected_kinds:
            tracker = self.tracker_builder(
                kind, project.trackers.get(kind, {})
            )
            if tracker is None:
                raise PlanError(f"Неизвестный трекер: {kind}")
            if not tracker.is_configured():
                raise PlanError(f"Трекер {tracker.label} не настроен")
            try:
                worklogs = tracker.get_worklogs(start, end)
            except Exception as exc:
                raise PlanError(f"Трекер {tracker.label}: {exc}") from exc
            for worklog in worklogs:
                existing[worklog.date] = (
                    existing.get(worklog.date, 0) + worklog.hours
                )
        return existing

    def _build_days(
        self,
        project: ProjectConfig,
        start: date,
        end: date,
        existing: dict[str, float],
    ) -> list[DayPlanDTO]:
        result: list[DayPlanDTO] = []
        current = start
        while current <= end:
            iso = current.isoformat()
            target = (
                project.workday_hours
                if current.weekday() < 5 and iso not in project.exclude_dates
                else 0.0
            )
            existing_hours = round(existing.get(iso, 0.0), 2)
            deficit = max(0.0, round(target - existing_hours, 2))
            result.append(
                DayPlanDTO(
                    date=iso,
                    existing_hours=existing_hours,
                    deficit_hours=deficit,
                    planned_hours=0.0,
                )
            )
            current += timedelta(days=1)
        return result

    def _apply_ai_response(
        self,
        days: list[DayPlanDTO],
        raw: dict,
        commits: list[GitCommitDTO],
    ) -> CommitPlanDTO:
        by_date = {day.date: day for day in days}
        known_hashes = {commit.hash for commit in commits}
        for item in raw.get("days", []):
            if not isinstance(item, dict):
                continue
            day = by_date.get(str(item.get("date", "")))
            if day is None:
                self.log(f"ИИ вернул дату вне периода: {item.get('date')}")
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
                [
                    value
                    for value in hashes
                    if isinstance(value, str) and value in known_hashes
                ]
                if isinstance(hashes, list)
                else []
            )
            confidence = str(item.get("confidence", "low")).lower()
            day.confidence = (
                confidence
                if confidence in {"high", "medium", "low"}
                else "low"
            )

        return CommitPlanDTO(
            summary=str(raw.get("summary", "")).strip(),
            days=days,
            raw_response=json.dumps(raw, ensure_ascii=False),
        )
```

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_commit_plan_service.py -q`
Expected: PASS.

```bash
git add dto/commit_plan_dto.py services/commit_plan_service.py tests/test_commit_plan_service.py
git commit -m "feat: build AI worklog plan from commits and deficits"
```

---

### Task 9: GUI shell, список проектов и редактор

**Files:**
- Create: `gui/project_validation.py`
- Create: `gui/project_editor.py`
- Create: `gui/project_list_view.py`
- Create: `gui/project_view.py`
- Modify: `gui/app.py`
- Modify: `fill_redmine_gui.py`
- Create: `tests/test_project_validation.py`

**Interfaces:**
- Consumes: `ProjectRepository`, `ProjectConfig`, `all_trackers`, `GitClient`.
- Produces:
  - `validate_project_form(form, exclude_dates, tracker_values, ai_values, db_id=None) -> tuple[ProjectConfig | None, list[str]]`
  - `parse_period(start_text, end_text) -> tuple[date, date]`
  - `ProjectEditor(parent, repo, project=None)` с `result: ProjectConfig | None`
  - `ProjectListView(parent, repo, on_open)`
  - `ProjectView(parent, project, repo, worker, service, on_back, on_project_updated)`
  - `MainWindow` с навигацией.

- [ ] **Step 1: Write failing validation tests**

```python
# tests/test_project_validation.py
from datetime import date

from gui.project_validation import parse_period, validate_project_form


def test_valid_project_form():
    project, errors = validate_project_form(
        form={"name": "Проект", "git_repo_path": "/tmp/repo", "git_author_email": "me@example.com", "workday_hours": "8"},
        exclude_dates=["2026-10-05"],
        tracker_values={
            "redmine": {
                "api_key": "key",
                "user_id": "16",
                "activity_id": "9",
                "issue_id": "2682",
                "comment": "dev",
            }
        },
        ai_values={"base_url": "https://api.example/v1", "model": "m", "api_key": "k"},
    )

    assert errors == []
    assert project.name == "Проект"
    assert project.workday_hours == 8.0
    assert project.trackers["redmine"]["user_id"] == 16
    assert project.ai["model"] == "m"


def test_empty_name_is_rejected():
    project, errors = validate_project_form(
        form={"name": " ", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={},
        ai_values={},
    )

    assert project is None
    assert "Имя проекта обязательно" in errors


def test_bad_workday_is_rejected():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "25"},
        exclude_dates=[],
        tracker_values={},
        ai_values={},
    )

    assert project is None
    assert any("рабочий день" in error.lower() for error in errors)


def test_partial_tracker_is_rejected():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={"redmine": {"api_key": "key"}},
        ai_values={},
    )

    assert project is None
    assert any("Redmine" in error for error in errors)


def test_empty_tracker_is_allowed():
    project, errors = validate_project_form(
        form={"name": "P", "workday_hours": "8"},
        exclude_dates=[],
        tracker_values={"redmine": {}},
        ai_values={},
    )

    assert errors == []
    assert project.trackers == {}


def test_parse_period():
    start, end = parse_period("2026-10-01", "2026-10-31")
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)


def test_parse_period_rejects_reverse_order():
    try:
        parse_period("2026-10-31", "2026-10-01")
    except ValueError as exc:
        assert "позже" in str(exc)
    else:
        raise AssertionError("expected ValueError")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_validation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.project_validation'`.

- [ ] **Step 3: Implement validation**

```python
# gui/project_validation.py
from datetime import date

from configs.project_config import ProjectConfig
from trackers.registry import all_trackers


def _int_value(value, label: str, errors: list[str]) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_project_form(
    form: dict[str, str],
    exclude_dates: list[str],
    tracker_values: dict[str, dict],
    ai_values: dict[str, str],
    db_id: int | None = None,
) -> tuple[ProjectConfig | None, list[str]]:
    errors: list[str] = []
    name = form.get("name", "").strip()
    if not name:
        errors.append("Имя проекта обязательно")

    try:
        workday_hours = float(form.get("workday_hours", "8"))
    except (TypeError, ValueError):
        errors.append("Рабочий день: должно быть числом")
        workday_hours = 8.0
    if not 0 < workday_hours <= 24:
        errors.append("Рабочий день: должно быть больше 0 и не больше 24")

    trackers: dict[str, dict] = {}
    for cls in all_trackers():
        values = tracker_values.get(cls.kind, {})
        cls_errors = cls.validate_config(values)
        errors.extend(cls_errors)
        if cls_errors or not any(
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

    ai = {
        key: value.strip()
        for key, value in ai_values.items()
        if value.strip()
    }
    base_url = ai.get("base_url", "")
    if base_url and not base_url.startswith(("http://", "https://")):
        errors.append("ИИ: base_url должен начинаться с http:// или https://")

    if errors:
        return None, errors

    return (
        ProjectConfig(
            name=name,
            git_repo_path=form.get("git_repo_path", "").strip(),
            git_author_email=form.get("git_author_email", "").strip(),
            workday_hours=workday_hours,
            exclude_dates=sorted(exclude_dates),
            trackers=trackers,
            ai=ai,
            db_id=db_id,
        ),
        [],
    )


def parse_period(start_text: str, end_text: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_text.strip())
        end = date.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ValueError("Даты должны быть в формате ГГГГ-ММ-ДД") from exc
    if start > end:
        raise ValueError("Начало периода позже конца")
    return start, end
```

- [ ] **Step 4: Implement ProjectEditor**

```python
# gui/project_editor.py
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from clients.git_client import GitClient, GitError
from configs.project_config import ProjectConfig
from gui.project_validation import validate_project_form
from gui.validation import parse_exclude_date
from storage.project_repository import ProjectRepository
from trackers.registry import all_trackers


class ProjectEditor(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        repo: ProjectRepository,
        project: ProjectConfig | None = None,
    ):
        super().__init__(parent)
        self.repo = repo
        self.project = project
        self.result: ProjectConfig | None = None
        self.exclude_dates = list(project.exclude_dates) if project else []
        self.fields: dict[str, ttk.Entry] = {}
        self.tracker_entries: dict[str, dict[str, ttk.Entry]] = {}
        self.ai_entries: dict[str, ttk.Entry] = {}
        self.secret_entries: list[ttk.Entry] = []
        self.show_secrets = tk.BooleanVar(value=False)

        self.title("Настройки проекта" if project else "Новый проект")
        self.geometry("720x680")
        self.minsize(640, 560)
        self._build()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_general(notebook)
        self._build_trackers(notebook)
        self._build_ai(notebook)

        footer = ttk.Frame(self, padding=(8, 0, 8, 8))
        footer.pack(fill="x")
        self.error_label = ttk.Label(footer, text="", foreground="red", wraplength=660)
        self.error_label.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Сохранить", command=self._save).pack(side="right", padx=4)
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
        value: str = "",
        secret: bool = False,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=52, show="*" if secret else "")
        entry.grid(row=row, column=1, sticky="we", pady=3)
        if value:
            entry.insert(0, value)
        if secret:
            self.secret_entries.append(entry)
        return entry

    def _build_general(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Общее")
        frame.columnconfigure(1, weight=1)
        project = self.project

        self.fields["name"] = self._entry(
            frame, 0, "name", "Имя", project.name if project else ""
        )
        self.fields["git_repo_path"] = self._entry(
            frame, 1, "git_repo_path", "Git-репозиторий",
            project.git_repo_path if project else "",
        )
        ttk.Button(frame, text="Выбрать…", command=self._browse_repo).grid(
            row=1, column=2, padx=4
        )
        self.fields["git_author_email"] = self._entry(
            frame, 2, "git_author_email", "Email автора",
            project.git_author_email if project else "",
        )
        ttk.Button(frame, text="Из git", command=self._email_from_git).grid(
            row=2, column=2, padx=4
        )
        self.fields["workday_hours"] = self._entry(
            frame, 3, "workday_hours", "Рабочий день, ч",
            str(project.workday_hours) if project else "8",
        )

        dates_frame = ttk.LabelFrame(frame, text="Исключённые даты", padding=6)
        dates_frame.grid(row=4, column=0, columnspan=3, sticky="we", pady=(10, 0))
        self.dates_list = tk.Listbox(dates_frame, height=4, width=18)
        self.dates_list.grid(row=0, column=0, rowspan=3, sticky="we")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry = ttk.Entry(dates_frame, width=16)
        self.date_entry.grid(row=0, column=1, padx=6)
        ttk.Button(dates_frame, text="Добавить", command=self._add_date).grid(
            row=1, column=1, padx=6, sticky="we"
        )
        ttk.Button(dates_frame, text="Удалить", command=self._remove_date).grid(
            row=2, column=1, padx=6, sticky="we"
        )

    def _build_trackers(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Трекеры")
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Checkbutton(
            content,
            text="показать секреты",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).pack(anchor="w", pady=(0, 6))

        for cls in all_trackers():
            section = ttk.LabelFrame(content, text=cls.label, padding=8)
            section.pack(fill="x", pady=4)
            section.columnconfigure(1, weight=1)
            values = (self.project.trackers.get(cls.kind, {}) if self.project else {})
            entries: dict[str, ttk.Entry] = {}
            for row, field in enumerate(cls.fields):
                entries[field.key] = self._entry(
                    section,
                    row,
                    field.key,
                    field.label,
                    str(values.get(field.key, "")),
                    secret=field.kind == "secret",
                )
            self.tracker_entries[cls.kind] = entries

    def _build_ai(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="ИИ")
        frame.columnconfigure(1, weight=1)
        values = self.project.ai if self.project else {}
        self.ai_entries["base_url"] = self._entry(
            frame, 0, "base_url", "Base URL",
            str(values.get("base_url", "")),
        )
        self.ai_entries["model"] = self._entry(
            frame, 1, "model", "Модель", str(values.get("model", ""))
        )
        self.ai_entries["api_key"] = self._entry(
            frame, 2, "api_key", "API key",
            str(values.get("api_key", "")), secret=True,
        )
        ttk.Label(
            frame,
            text="Пустые поля берутся из OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY.",
            wraplength=600,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _browse_repo(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.fields["git_repo_path"].delete(0, "end")
            self.fields["git_repo_path"].insert(0, path)

    def _email_from_git(self) -> None:
        path = self.fields["git_repo_path"].get().strip()
        if not path:
            messagebox.showinfo("Work Assistant", "Сначала выберите репозиторий", parent=self)
            return
        try:
            email = GitClient(path).get_config_email()
        except GitError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        self.fields["git_author_email"].delete(0, "end")
        self.fields["git_author_email"].insert(0, email)

    def _toggle_secrets(self) -> None:
        show = "" if self.show_secrets.get() else "*"
        for entry in self.secret_entries:
            entry.configure(show=show)

    def _add_date(self) -> None:
        parsed, error = parse_exclude_date(self.date_entry.get(), self.exclude_dates)
        if error:
            self.error_label.configure(text=error)
            return
        self.exclude_dates.append(parsed)
        self.exclude_dates.sort()
        self.dates_list.delete(0, "end")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry.delete(0, "end")
        self.error_label.configure(text="")

    def _remove_date(self) -> None:
        selection = self.dates_list.curselection()
        if not selection:
            return
        value = self.dates_list.get(selection[0])
        self.dates_list.delete(selection[0])
        self.exclude_dates.remove(value)

    def _save(self) -> None:
        form = {key: entry.get() for key, entry in self.fields.items()}
        tracker_values = {
            kind: {key: entry.get() for key, entry in entries.items()}
            for kind, entries in self.tracker_entries.items()
        }
        ai_values = {
            key: entry.get() for key, entry in self.ai_entries.items()
        }
        project, errors = validate_project_form(
            form,
            exclude_dates=self.exclude_dates,
            tracker_values=tracker_values,
            ai_values=ai_values,
            db_id=self.project.db_id if self.project else None,
        )
        if errors:
            self.error_label.configure(text="\n".join(errors))
            return
        existing = self.repo.find_by_name(project.name)
        if existing is not None and existing.db_id != project.db_id:
            self.error_label.configure(text="Проект с таким именем уже существует")
            return
        if self.project is not None and "selected_trackers" in self.project.ai:
            project.ai["selected_trackers"] = self.project.ai["selected_trackers"]
        self.result = project
        self.destroy()
```

- [ ] **Step 5: Implement project list**

```python
# gui/project_list_view.py
from collections.abc import Callable
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_editor import ProjectEditor
from storage.project_repository import ProjectRepository
from trackers.registry import configured_trackers


class ProjectListView(ttk.Frame):
    def __init__(
        self,
        parent,
        repo: ProjectRepository,
        on_open: Callable[[ProjectConfig], None],
    ):
        super().__init__(parent, padding=6)
        self.repo = repo
        self.on_open = on_open
        self.projects_by_iid: dict[str, ProjectConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="+", width=3, command=self.add_project).pack(
            side="left", padx=2
        )
        for text, command in (
            ("Открыть", self.open_project),
            ("Настройки", self.edit_project),
            ("Удалить", self.delete_project),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(
                side="left", padx=2
            )

        self.tree = ttk.Treeview(
            self,
            columns=("name", "git", "trackers"),
            show="headings",
            height=16,
        )
        for column, (title, width) in {
            "name": ("Проект", 220),
            "git": ("Git-репозиторий", 420),
            "trackers": ("Трекеры", 220),
        }.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda event: self.open_project())
        self.tree.bind("<Return>", lambda event: self.open_project())

        self.empty_label = ttk.Label(
            self,
            text="Нажмите +, чтобы добавить проект",
            foreground="#777",
        )
        self.empty_label.pack(anchor="w")

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.projects_by_iid.clear()
        projects = self.repo.list_projects()
        for project in projects:
            labels = ", ".join(
                tracker.label for tracker in configured_trackers(project)
            )
            iid = self.tree.insert(
                "",
                "end",
                values=(project.name, project.git_repo_path or "—", labels or "—"),
            )
            self.projects_by_iid[iid] = project
        if projects:
            self.empty_label.pack_forget()
        else:
            self.empty_label.pack(anchor="w")

    def selected_project(self, show_message: bool = True) -> ProjectConfig | None:
        selection = self.tree.selection()
        if not selection:
            if show_message:
                messagebox.showinfo("Work Assistant", "Выберите проект", parent=self)
            return None
        return self.projects_by_iid[selection[0]]

    def add_project(self) -> None:
        editor = ProjectEditor(self, self.repo, None)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.add_project(editor.result)
            self.refresh()

    def edit_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        editor = ProjectEditor(self, self.repo, project)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.update_project(project.db_id, editor.result)
            self.refresh()

    def delete_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        if messagebox.askyesno(
            "Work Assistant",
            f"Удалить проект «{project.name}»?",
            parent=self,
        ):
            self.repo.delete_project(project.db_id)
            self.refresh()

    def open_project(self) -> None:
        project = self.selected_project(show_message=False)
        if project is not None:
            self.on_open(project)
```

- [ ] **Step 6: Implement project view shell and MainWindow**

```python
# gui/project_view.py
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_editor import ProjectEditor
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.project_repository import ProjectRepository


class ProjectView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        worker: GuiWorker,
        service: ImportService,
        on_back: Callable[[], None],
        on_project_updated: Callable[[ProjectConfig], None],
    ):
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.worker = worker
        self.service = service
        self.on_back = on_back
        self.on_project_updated = on_project_updated

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(header, text="← Проекты", command=self._back).pack(side="left")
        ttk.Label(
            header,
            text=project.name,
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side="left", padx=12)
        ttk.Button(header, text="Настройки", command=self._settings).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, pady=6)
        self._build_placeholders()

    def _build_placeholders(self) -> None:
        for title in ("Redmine", "YouTrack → Redmine", "Коммиты и план"):
            frame = ttk.Frame(self.notebook, padding=12)
            ttk.Label(frame, text="Вкладка будет добавлена следующим шагом").pack()
            self.notebook.add(frame, text=title)

    @property
    def busy(self) -> bool:
        return False

    def _back(self) -> None:
        if self.busy and not messagebox.askyesno(
            "Work Assistant", "Идёт работа. Вернуться к списку проектов?", parent=self
        ):
            return
        self.on_back()

    def _settings(self) -> None:
        if self.busy:
            messagebox.showinfo("Work Assistant", "Дождитесь завершения работы", parent=self)
            return
        editor = ProjectEditor(self, self.repo, self.project)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.update_project(self.project.db_id, editor.result)
            self.on_project_updated(editor.result)
```

```python
# gui/app.py
import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_list_view import ProjectListView
from gui.project_view import ProjectView
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.project_repository import ProjectRepository


class MainWindow(tk.Tk):
    def __init__(self, repo: ProjectRepository):
        super().__init__()
        self.repo = repo
        self.worker = GuiWorker(self)
        self.service = ImportService(log=lambda message: self.status.set(message))
        self.current_view: tk.Widget | None = None

        self.title("Work Assistant")
        self.geometry("1100x780")
        self.minsize(900, 620)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self,
            textvariable=self.status,
            relief="sunken",
            anchor="w",
            padding=2,
        ).pack(fill="x", side="bottom")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_project_list()

    def _set_view(self, view: tk.Widget) -> None:
        if self.current_view is not None:
            self.current_view.destroy()
        self.current_view = view
        view.pack(fill="both", expand=True)

    def show_project_list(self) -> None:
        self.status.set("готово")
        self._set_view(
            ProjectListView(self.container, self.repo, on_open=self.show_project)
        )

    def show_project(self, project: ProjectConfig) -> None:
        self.status.set(project.name)
        self._set_view(
            ProjectView(
                self.container,
                project=project,
                repo=self.repo,
                worker=self.worker,
                service=self.service,
                on_back=self.show_project_list,
                on_project_updated=self.show_project,
            )
        )

    def _on_close(self) -> None:
        busy = bool(getattr(self.current_view, "busy", False))
        if busy and not messagebox.askyesno(
            "Work Assistant", "Работа выполняется. Закрыть окно?", parent=self
        ):
            return
        self.destroy()
```

- [ ] **Step 7: Update GUI entry point**

Замените `fill_redmine_gui.py` на:

```python
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository
from gui.app import MainWindow


def main() -> None:
    migrate_default_legacy_database(log=print)
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo, log=print)
    migrate_users_to_projects(project_repo, user_repo, log=print)
    app = MainWindow(project_repo)
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 8: Run tests and compile check**

Run: `pytest tests/test_project_validation.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

Run: `python -m py_compile gui/project_validation.py gui/project_editor.py gui/project_list_view.py gui/project_view.py gui/app.py fill_redmine_gui.py`
Expected: exit 0.

- [ ] **Step 9: Commit**

```bash
git add gui/project_validation.py gui/project_editor.py gui/project_list_view.py gui/project_view.py gui/app.py fill_redmine_gui.py tests/test_project_validation.py
git commit -m "feat: add project list, navigation and editor"
```

---

### Task 10: Проектный импорт Redmine и YouTrack → Redmine

**Files:**
- Create: `dto/import_action.py`
- Modify: `dto/preview_dto.py`
- Modify: `services/preview_service.py`
- Modify: `services/import_service.py`
- Modify: `imports/base_importer.py`
- Modify: `imports/manual_import.py`
- Modify: `imports/youtrack_import.py`
- Modify: `imports/import_factory.py`
- Modify: `fill_redmine.py`
- Replace tests: `tests/test_manual_import.py`, `tests/test_youtrack_import.py`, `tests/test_preview_service.py`, `tests/test_import_service.py`, `tests/test_import_factory.py`, `tests/test_integration.py`, `tests/test_fill_redmine.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `BaseTracker`, существующие клиенты.
- Produces:
  - `ImportAction.REDMINE_FILL`, `ImportAction.YOUTRACK_TRANSFER` (str enum).
  - `PreviewDTO(project_name, action, issue_id, comment, ..., ranges, total_hours, error)`.
  - `ImportService.prepare(project, action) -> PrepareResult`
  - `ImportService.prepare_many(projects, action) -> PrepareResult`
  - `ImportService.run(items, progress_cb=None) -> ImportSummary`
  - `create_importer(project, action) -> BaseImporter`
  - `PreparedImport(project, action, importer, records, preview)`

- [ ] **Step 1: Write failing tests for project import**

```python
# tests/test_import_factory.py
import pytest

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Проект",
        exclude_dates=[],
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "dev",
            },
            "youtrack": {"access_token": "token"},
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


def test_creates_manual_importer():
    assert isinstance(
        create_importer(make_project(), ImportAction.REDMINE_FILL),
        ManualImporter,
    )


def test_creates_youtrack_importer():
    assert isinstance(
        create_importer(make_project(), ImportAction.YOUTRACK_TRANSFER),
        YoutrackImporter,
    )


def test_unknown_action_raises():
    with pytest.raises(ValueError):
        create_importer(make_project(), "unknown")
```

```python
# tests/test_manual_import.py
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from imports.manual_import import ManualImporter


@pytest.fixture
def project():
    return ProjectConfig(
        name="Проект",
        exclude_dates=["2026-02-15"],
        trackers={
            "redmine": {
                "api_key": "test_api_key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test",
            }
        },
    )


@pytest.fixture
def importer(project):
    return ManualImporter(project)


def test_create_record_list_returns_date_hours_dto(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert isinstance(records, list)
    assert all(isinstance(record, DateHoursDTO) for record in records)


def test_create_record_list_excludes_weekends(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert all(date.fromisoformat(record.date).weekday() < 5 for record in records)


def test_create_record_list_excludes_exclude_dates(importer):
    with patch.object(importer, "get_times", return_value=set()):
        records = importer.create_record_list()

    assert "2026-02-15" not in [record.date for record in records]


def test_create_record_list_excludes_already_spent_dates(importer):
    with patch.object(importer, "get_times", return_value={"2026-02-02"}):
        records = importer.create_record_list()

    assert "2026-02-02" not in [record.date for record in records]


def test_get_times_uses_redmine_config(importer):
    with patch(
        "imports.manual_import.RedmineClient.get_spent_on_dates",
        return_value={"2026-02-01"},
    ) as mock_get:
        result = importer.get_times()

    assert result == {"2026-02-01"}
    mock_get.assert_called_once_with(user_id=1, issue_id=123)


def test_missing_redmine_config_raises(project):
    project.trackers = {}
    importer = ManualImporter(project)

    with pytest.raises(ValueError, match="Redmine"):
        importer.create_record_list()
```

```python
# tests/test_youtrack_import.py
from datetime import datetime
from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from imports.youtrack_import import YoutrackImporter


@pytest.fixture
def project():
    return ProjectConfig(
        name="Проект",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test",
            },
            "youtrack": {"access_token": "test_token"},
        },
    )


def test_aggregates_hours_by_date(project):
    importer = YoutrackImporter(project)
    with patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[
            {"date": 1704067200000, "duration": {"minutes": 240}},
            {"date": 1704067200000, "duration": {"minutes": 240}},
        ],
    ):
        records = importer.create_record_list()

    assert len(records) == 1
    assert isinstance(records[0], DateHoursDTO)
    assert records[0].hours == 8.0


def test_uses_bearer_token(project):
    importer = YoutrackImporter(project)
    with patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[],
    ) as mock_get:
        importer.create_record_list()

    mock_get.assert_called_once()


def test_requests_current_month(project):
    importer = YoutrackImporter(project)
    fixed = datetime(2026, 4, 30, 12, 0, 0)
    with patch("imports.youtrack_import.datetime") as mock_datetime, patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[],
    ) as mock_get:
        mock_datetime.now.return_value = fixed
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_datetime.fromtimestamp.side_effect = datetime.fromtimestamp
        importer.create_record_list()

    _, kwargs = mock_get.call_args
    assert kwargs["start_date"] == datetime(2026, 4, 1)
    assert kwargs["end_date"] == datetime(2026, 5, 1)


def test_missing_youtrack_token_raises(project):
    project.trackers.pop("youtrack")
    importer = YoutrackImporter(project)

    with pytest.raises(ValueError, match="YouTrack"):
        importer.create_record_list()
```

```python
# tests/test_preview_service.py
from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.preview_service import PreviewService


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Олег",
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            }
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема задачи",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


def test_groups_consecutive_days_with_equal_hours():
    records = [
        DateHoursDTO(date="2026-10-01", hours=8),
        DateHoursDTO(date="2026-10-02", hours=8),
        DateHoursDTO(date="2026-10-05", hours=4),
    ]

    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", records, make_issue_info()
    )

    assert [(r.start_date, r.end_date, r.hours) for r in preview.ranges] == [
        ("2026-10-01", "2026-10-02", 8),
        ("2026-10-05", "2026-10-05", 4),
    ]
    assert preview.total_hours == 20


def test_copies_project_fields():
    preview = PreviewService.build_preview(
        make_project(),
        "youtrack_transfer",
        [DateHoursDTO(date="2026-10-01", hours=8)],
        make_issue_info(),
    )

    assert preview.project_name == "Олег"
    assert preview.action == "youtrack_transfer"
    assert preview.issue_id == 2682
    assert preview.comment == "development"
    assert preview.issue_subject == "Тема задачи"
    assert preview.issue_url == "http://redmine/issues/2682"


def test_error_is_stored():
    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", [], None, error="сбой сети"
    )

    assert preview.error == "сбой сети"
    assert preview.ranges == []
    assert preview.total_hours == 0


def test_print_preview_uses_project_name(capsys):
    preview = PreviewService.build_preview(
        make_project(), "redmine_fill", [], None, error="сбой сети"
    )

    PreviewService.print_preview(preview)

    output = capsys.readouterr().out
    assert "=== Project: Олег ===" in output
    assert "Ошибка: сбой сети" in output
```

```python
# tests/test_import_service.py
from unittest.mock import patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from services.import_service import (
    ImportService,
    ImportSummary,
    PrepareResult,
    PreparedImport,
)
from services.preview_service import PreviewService


def make_project(name="Олег") -> ProjectConfig:
    return ProjectConfig(
        name=name,
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 16,
                "activity_id": 9,
                "issue_id": 2682,
                "comment": "development",
            }
        },
    )


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


class FakeImporter:
    def __init__(self, records=None, errors=None):
        self.records = records or []
        self.errors = errors or []
        self.create_calls = 0
        self.handle_calls = []
        self.progress_callbacks = []

    def create_record_list(self):
        self.create_calls += 1
        return self.records

    async def handle(self, records=None, on_progress=None):
        self.handle_calls.append(records)
        self.progress_callbacks.append(on_progress)
        if on_progress is not None:
            for completed in range(1, len(records) + 1):
                on_progress(completed, len(records))
        return list(self.errors)


def test_prepare_builds_preview(monkeypatch):
    importer = FakeImporter(records=[DateHoursDTO(date="2026-10-01", hours=8)])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )
    monkeypatch.setattr(
        "services.import_service.PreviewService.get_issue_info",
        lambda cache, project: make_issue_info(),
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert len(result.items) == 1
    assert result.errors == []
    assert result.items[0].project.name == "Олег"
    assert result.items[0].action is ImportAction.REDMINE_FILL
    assert result.items[0].preview.project_name == "Олег"


def test_prepare_reports_importer_error(monkeypatch):
    class BrokenImporter:
        def create_record_list(self):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: BrokenImporter(),
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert result.items == []
    assert len(result.errors) == 1
    assert "network down" in result.errors[0].error


def test_prepare_skips_empty_records(monkeypatch):
    importer = FakeImporter(records=[])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )

    result = ImportService(log=lambda message: None).prepare(
        make_project(), ImportAction.REDMINE_FILL
    )

    assert result.items == []
    assert result.errors == []


def test_prepare_many_merges(monkeypatch):
    importer = FakeImporter(records=[DateHoursDTO(date="2026-10-01", hours=8)])
    monkeypatch.setattr(
        "services.import_service.create_importer",
        lambda project, action: importer,
    )
    monkeypatch.setattr(
        "services.import_service.PreviewService.get_issue_info",
        lambda cache, project: None,
    )

    result = ImportService(log=lambda message: None).prepare_many(
        [make_project("A"), make_project("B")], ImportAction.REDMINE_FILL
    )

    assert [item.project.name for item in result.items] == ["A", "B"]


@pytest.mark.asyncio
async def test_run_reports_progress_and_errors():
    project = make_project()
    importer = FakeImporter(
        records=[
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=8),
        ],
        errors=[("2026-10-01", "500 error")],
    )
    items = [
        PreparedImport(
            project=project,
            action=ImportAction.REDMINE_FILL,
            importer=importer,
            records=importer.records,
            preview=PreviewService.build_preview(
                project, "redmine_fill", importer.records, None
            ),
        )
    ]
    progress = []

    summary = await ImportService(log=lambda message: None).run(
        items,
        progress_cb=lambda completed, total, name: progress.append(
            (completed, total, name)
        ),
    )

    assert progress == [(1, 2, "Олег"), (2, 2, "Олег")]
    assert summary == ImportSummary(
        total=2, errors=[("Олег", "2026-10-01", "500 error")]
    )


@pytest.mark.asyncio
async def test_run_without_items_returns_empty_summary():
    summary = await ImportService(log=lambda message: None).run([])

    assert summary.total == 0
    assert summary.errors == []
```

```python
# tests/test_integration.py
from unittest.mock import MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.import_factory import create_importer
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


class MockResponse:
    status = 201

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockSession:
    def post(self, *args, **kwargs):
        return MockResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def make_project(**overrides) -> ProjectConfig:
    data = dict(
        name="Test",
        trackers={
            "redmine": {
                "api_key": "test_api_key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test work",
            },
            "youtrack": {"access_token": "test_token"},
        },
    )
    data.update(overrides)
    return ProjectConfig(**data)


@pytest.mark.asyncio
async def test_full_manual_import_flow_with_mocks():
    importer = ManualImporter(make_project())

    with patch.object(importer, "get_times", return_value=set()), patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.aiohttp.ClientSession",
        return_value=MockSession(),
    ):
        records = importer.create_record_list()
        assert records
        await importer.handle()


@pytest.mark.asyncio
async def test_full_youtrack_import_flow_with_mocks():
    importer = YoutrackImporter(make_project())

    with patch(
        "imports.youtrack_import.YoutrackClient.get_work_items",
        return_value=[{"date": 1704067200000, "duration": {"minutes": 480}}],
    ), patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.aiohttp.ClientSession",
        return_value=MockSession(),
    ):
        records = importer.create_record_list()
        assert records
        await importer.handle()


def test_factory_returns_importers():
    assert isinstance(
        create_importer(make_project(), ImportAction.REDMINE_FILL),
        ManualImporter,
    )
    assert isinstance(
        create_importer(make_project(), ImportAction.YOUTRACK_TRANSFER),
        YoutrackImporter,
    )
```

```python
# tests/test_fill_redmine.py
from unittest.mock import MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from fill_redmine import main
from services.issue_service import IssueService


def make_project() -> ProjectConfig:
    return ProjectConfig(
        name="Test Project",
        db_id=1,
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test work",
            }
        },
    )


def test_format_created_on_formats_iso_datetime():
    assert (
        IssueService.format_created_on("2026-03-31T08:13:51Z")
        == "2026-03-31 08:13:51 UTC"
    )


def test_get_issue_info_returns_subject_author_and_url():
    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine/",
    ), patch("clients.redmine_client.requests.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "issue": {
                "subject": "Issue title",
                "author": {"name": "Oleg"},
                "created_on": "2026-03-31T08:13:51Z",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = IssueService.get_issue_info(issue_id=2574, api_key="key")

    assert result == IssueInfoDTO(
        subject="Issue title",
        url="http://redmine/issues/2574",
        author="Oleg",
        created_on="2026-03-31 08:13:51 UTC",
    )


@pytest.mark.asyncio
async def test_main_prints_project_preview(capsys):
    mock_importer = MagicMock()
    mock_importer.create_record_list.return_value = [
        DateHoursDTO(date="2026-03-31", hours=8)
    ]
    mock_importer.handle.return_value = []
    mock_repo = MagicMock()
    mock_repo.get_project.return_value = make_project()

    with patch(
        "services.import_service.create_importer",
        return_value=mock_importer,
    ), patch(
        "services.import_service.PreviewService.get_issue_info",
        return_value=IssueInfoDTO(
            subject="Issue title",
            url="http://redmine/issues/123",
            author="Oleg",
            created_on="2026-03-30 10:00:00 UTC",
        ),
    ), patch("builtins.input", return_value="n"):
        await main(
            project_id=1,
            action=ImportAction.REDMINE_FILL,
            repo=mock_repo,
        )

    output = capsys.readouterr().out
    assert "=== Project: Test Project ===" in output
    assert "Issue: Issue title" in output
    assert output.index("Issue: Issue title") < output.index("Dates:")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_import_factory.py tests/test_manual_import.py tests/test_youtrack_import.py tests/test_preview_service.py tests/test_import_service.py tests/test_integration.py tests/test_fill_redmine.py -q`
Expected: FAIL (новые импорты/поля отсутствуют).

- [ ] **Step 4: Implement DTOs and preview service**

```python
# dto/import_action.py
from enum import Enum


class ImportAction(str, Enum):
    REDMINE_FILL = "redmine_fill"
    YOUTRACK_TRANSFER = "youtrack_transfer"

    @property
    def label(self) -> str:
        labels = {
            self.REDMINE_FILL: "Redmine",
            self.YOUTRACK_TRANSFER: "YouTrack → Redmine",
        }
        return labels[self]
```

```python
# dto/preview_dto.py
from dataclasses import dataclass, field


@dataclass
class DateRangeDTO:
    start_date: str
    end_date: str
    hours: int | float


@dataclass
class PreviewDTO:
    project_name: str
    action: str
    issue_id: int
    comment: str = ""
    issue_subject: str | None = None
    issue_url: str | None = None
    issue_author: str | None = None
    issue_created_on: str | None = None
    ranges: list[DateRangeDTO] = field(default_factory=list)
    total_hours: float = 0
    error: str | None = None
```

```python
# services/preview_service.py
from datetime import date

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import DateRangeDTO, PreviewDTO
from services.issue_service import IssueService


class PreviewService:
    @staticmethod
    def get_issue_info(
        issue_info_cache: dict[int, IssueInfoDTO | None],
        project: ProjectConfig,
    ) -> IssueInfoDTO | None:
        config = project.trackers.get("redmine", {})
        issue_id = config.get("issue_id")
        api_key = config.get("api_key", "")
        if not issue_id or not api_key:
            return None

        issue_id = int(issue_id)
        if issue_id not in issue_info_cache:
            issue_info_cache[issue_id] = IssueService.get_issue_info(
                issue_id=issue_id,
                api_key=api_key,
            )
        return issue_info_cache[issue_id]

    @staticmethod
    def build_preview(
        project: ProjectConfig,
        action: str,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
        error: str | None = None,
    ) -> PreviewDTO:
        ranges: list[DateRangeDTO] = []
        total_hours: float = 0

        if records:
            range_start = records[0]
            prev = records[0]
            range_count = 1

            for record in records[1:]:
                prev_dt = date.fromisoformat(prev.date)
                curr_dt = date.fromisoformat(record.date)
                if record.hours == prev.hours and (curr_dt - prev_dt).days == 1:
                    prev = record
                    range_count += 1
                else:
                    ranges.append(
                        DateRangeDTO(range_start.date, prev.date, range_start.hours)
                    )
                    total_hours += range_count * range_start.hours
                    range_start = record
                    prev = record
                    range_count = 1

            ranges.append(DateRangeDTO(range_start.date, prev.date, range_start.hours))
            total_hours += range_count * range_start.hours

        config = project.trackers.get("redmine", {})
        issue_id = int(config.get("issue_id") or 0)
        return PreviewDTO(
            project_name=project.name,
            action=action,
            issue_id=issue_id,
            comment=config.get("comment", ""),
            issue_subject=issue_info.subject if issue_info else None,
            issue_url=issue_info.url if issue_info else None,
            issue_author=issue_info.author if issue_info else None,
            issue_created_on=issue_info.created_on if issue_info else None,
            ranges=ranges,
            total_hours=total_hours,
            error=error,
        )

    @staticmethod
    def print_header() -> None:
        print("\n" + "=" * 50)
        print("Time entries to be imported")
        print("=" * 50 + "\n")

    @staticmethod
    def print_preview(preview: PreviewDTO) -> None:
        print(f"=== Project: {preview.project_name} ===")
        print(f"Action: {preview.action}")
        if preview.error is not None:
            print(f"Ошибка: {preview.error}")
            print()
            return
        if preview.issue_subject is None:
            print(f"Issue Data: {preview.issue_id}")
        else:
            print(
                f"Issue Data: Id: {preview.issue_id}, "
                f"Author: {preview.issue_author}, Created: {preview.issue_created_on}"
            )
            print(f"Issue: {preview.issue_subject}")
            print(f"Issue URL: {preview.issue_url}")
        print(f"Comment: {preview.comment}")
        print("Dates:")
        for date_range in preview.ranges:
            if date_range.start_date == date_range.end_date:
                print(f"  {date_range.start_date} - {date_range.hours}h")
            else:
                print(
                    f"  {date_range.start_date} - {date_range.end_date} - "
                    f"{date_range.hours}h"
                )
        print(f"Total hours: {preview.total_hours}h")
        print()
```

- [ ] **Step 5: Refactor importers**

```python
# imports/base_importer.py
from abc import ABC, abstractmethod
from collections.abc import Callable

from clients.redmine_client import RedmineClient
from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):
    def __init__(self, project: ProjectConfig):
        self.project = project

    def redmine_config(self) -> dict:
        config = self.project.trackers.get("redmine", {})
        missing = [
            key
            for key in ("api_key", "user_id", "issue_id", "activity_id")
            if config.get(key) in (None, "")
        ]
        if missing:
            raise ValueError("Redmine не настроен: " + ", ".join(missing))
        return config

    def youtrack_token(self) -> str:
        token = self.project.trackers.get("youtrack", {}).get(
            "access_token", ""
        )
        if not token:
            raise ValueError("YouTrack не настроен: access_token")
        return token

    @abstractmethod
    def create_record_list(self) -> list[DateHoursDTO]:
        pass

    async def handle(
        self,
        records: list[DateHoursDTO] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        if records is None:
            records = self.create_record_list()

        config = self.redmine_config()
        return await self.update_redmine_activity(
            uid=int(config["user_id"]),
            iid=int(config["issue_id"]),
            comment=config.get("comment", ""),
            activity_id=int(config["activity_id"]),
            api_key=config["api_key"],
            records=records,
            on_progress=on_progress,
        )

    async def update_redmine_activity(
        self,
        uid: int,
        iid: int,
        comment: str,
        activity_id: int,
        api_key: str,
        records: list[DateHoursDTO],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        client = RedmineClient(api_key=api_key)
        return await client.create_time_entries(
            user_id=uid,
            issue_id=iid,
            comment=comment,
            activity_id=activity_id,
            records=records,
            on_progress=on_progress,
        )
```

```python
# imports/manual_import.py
import calendar
from datetime import date, timedelta

from clients.redmine_client import RedmineClient
from dto.date_hours_dto import DateHoursDTO
from imports.base_importer import BaseImporter


class ManualImporter(BaseImporter):
    def create_record_list(self) -> list[DateHoursDTO]:
        self.redmine_config()
        exclude_dates = self.project.exclude_dates
        start_day = date.today().replace(day=1)
        last_day = calendar.monthrange(start_day.year, start_day.month)[1]
        last_day = start_day.replace(day=last_day)

        spent_on_dates = self.get_times()
        records: list[DateHoursDTO] = []

        while start_day <= last_day:
            day_str = start_day.isoformat()
            if (
                start_day.weekday() < 5
                and day_str not in exclude_dates
                and day_str not in spent_on_dates
            ):
                records.append(DateHoursDTO(date=day_str, hours=8))
            start_day += timedelta(days=1)

        return records

    def get_times(self) -> set[str]:
        config = self.redmine_config()
        client = RedmineClient(api_key=config["api_key"])
        return client.get_spent_on_dates(
            user_id=int(config["user_id"]),
            issue_id=int(config["issue_id"]),
        )
```

```python
# imports/youtrack_import.py
from datetime import datetime

from clients.youtrack_client import YoutrackClient
from dto.date_hours_dto import DateHoursDTO
from imports.base_importer import BaseImporter


class YoutrackImporter(BaseImporter):
    def create_record_list(self) -> list[DateHoursDTO]:
        self.redmine_config()
        token = self.youtrack_token()
        now = datetime.now()
        first_day = datetime(now.year, now.month, 1)
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1)
        else:
            end_date = datetime(now.year, now.month + 1, 1)

        client = YoutrackClient(access_token=token)
        data = client.get_work_items(start_date=first_day, end_date=end_date)
        result: dict[str, float] = {}
        for item in data:
            item_date = datetime.fromtimestamp(item["date"] / 1000).strftime(
                "%Y-%m-%d"
            )
            minutes = float((item.get("duration") or {}).get("minutes", 0))
            result[item_date] = result.get(item_date, 0) + minutes / 60

        return [
            DateHoursDTO(date=item_date, hours=hours)
            for item_date, hours in sorted(result.items())
        ]
```

```python
# imports/import_factory.py
from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from imports.base_importer import BaseImporter
from imports.manual_import import ManualImporter
from imports.youtrack_import import YoutrackImporter


def create_importer(
    project: ProjectConfig, action: ImportAction
) -> BaseImporter:
    if action is ImportAction.REDMINE_FILL:
        return ManualImporter(project)
    if action is ImportAction.YOUTRACK_TRANSFER:
        return YoutrackImporter(project)
    raise ValueError(f"Неизвестное действие: {action}")
```

- [ ] **Step 6: Refactor ImportService**

Replace `services/import_service.py` with:

```python
from collections.abc import Callable
from dataclasses import dataclass, field

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import PreviewDTO
from imports.base_importer import BaseImporter
from imports.import_factory import create_importer
from services.preview_service import PreviewService


@dataclass
class PreparedImport:
    project: ProjectConfig
    action: ImportAction
    importer: BaseImporter
    records: list[DateHoursDTO]
    preview: PreviewDTO


@dataclass
class ImportSummary:
    total: int
    errors: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class PrepareResult:
    items: list[PreparedImport] = field(default_factory=list)
    errors: list[PreviewDTO] = field(default_factory=list)


class ImportService:
    def __init__(self, log: Callable[[str], None] = print):
        self.log = log

    def prepare(
        self, project: ProjectConfig, action: ImportAction
    ) -> PrepareResult:
        result = PrepareResult()
        try:
            importer = create_importer(project, action)
            records = importer.create_record_list()
        except Exception as exc:
            message = f"ошибка получения записей: {exc}"
            self.log(f"{project.name}: {message}")
            result.errors.append(self._error_preview(project, action, message))
            return result

        if not records:
            self.log(f"{project.name}: нет записей")
            return result

        issue_info_cache: dict[int, IssueInfoDTO | None] = {}
        issue_info = PreviewService.get_issue_info(issue_info_cache, project)
        preview = PreviewService.build_preview(
            project,
            action.value,
            records,
            issue_info,
        )
        result.items.append(
            PreparedImport(
                project=project,
                action=action,
                importer=importer,
                records=records,
                preview=preview,
            )
        )
        return result

    def prepare_many(
        self, projects: list[ProjectConfig], action: ImportAction
    ) -> PrepareResult:
        merged = PrepareResult()
        for project in projects:
            result = self.prepare(project, action)
            merged.items.extend(result.items)
            merged.errors.extend(result.errors)
        return merged

    @staticmethod
    def _error_preview(
        project: ProjectConfig, action: ImportAction, message: str
    ) -> PreviewDTO:
        return PreviewService.build_preview(
            project,
            action.value,
            [],
            None,
            error=message,
        )

    async def run(
        self,
        items: list[PreparedImport],
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> ImportSummary:
        total = sum(len(item.records) for item in items)
        errors: list[tuple[str, str, str]] = []
        completed_base = 0

        for item in items:
            def on_progress(
                completed: int,
                item_total: int,
                base: int = completed_base,
                name: str = item.project.name,
            ) -> None:
                if progress_cb is not None:
                    progress_cb(base + completed, total, name)

            item_errors = await item.importer.handle(
                records=item.records,
                on_progress=on_progress if progress_cb is not None else None,
            )
            for spent_on, message in item_errors or []:
                errors.append((item.project.name, spent_on, message))
            completed_base += len(item.records)

        return ImportSummary(total=total, errors=errors)
```

- [ ] **Step 7: Update CLI fill_redmine.py**

Replace with:

```python
import argparse
import asyncio

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from services.import_service import ImportService
from services.preview_service import PreviewService
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


async def main(
    project_id: int | None = None,
    action: ImportAction = ImportAction.REDMINE_FILL,
    override_issue_id: int | None = None,
    repo: ProjectRepository | None = None,
) -> None:
    repository = repo if repo is not None else ProjectRepository()
    if project_id is None:
        projects = repository.list_projects()
        if not projects:
            print("No projects found.")
            return
        for project in projects:
            print(f"{project.db_id}: {project.name}")
        return

    project = repository.get_project(project_id)
    if project is None:
        print(f"Project {project_id} not found.")
        return
    if override_issue_id:
        config = dict(project.trackers.get("redmine", {}))
        config["issue_id"] = override_issue_id
        project.trackers["redmine"] = config

    PreviewService.print_header()
    service = ImportService()
    result = service.prepare(project, action)

    for item in result.items:
        PreviewService.print_preview(item.preview)
    for preview in result.errors:
        PreviewService.print_preview(preview)

    if not result.items:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")
    summary = await service.run(result.items)
    success = summary.total - len(summary.errors)
    print(f"Import finished: {success} entries, {len(summary.errors)} errors.")


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=int, help="Project ID")
    parser.add_argument(
        "--action",
        choices=[action.value for action in ImportAction],
        default=ImportAction.REDMINE_FILL.value,
    )
    parser.add_argument("--id", type=int, help="Override Redmine issue ID")
    args = parser.parse_args()

    migrate_default_legacy_database()
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo)
    migrate_users_to_projects(project_repo, user_repo)
    asyncio.run(
        main(
            project_id=args.project,
            action=ImportAction(args.action),
            override_issue_id=args.id,
            repo=project_repo,
        )
    )


if __name__ == "__main__":
    cli()
```

- [ ] **Step 8: Run tests and fix leftovers**

Run: `pytest tests/test_import_factory.py tests/test_manual_import.py tests/test_youtrack_import.py tests/test_preview_service.py tests/test_import_service.py tests/test_integration.py tests/test_fill_redmine.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS. Если падают старые тесты, обновите их под новые сигнатуры; старые `UserConfig`-тесты (`test_user_config.py`, `test_user_repository.py`, `test_migration.py`) должны остаться без изменений.

- [ ] **Step 9: Commit**

```bash
git add dto/import_action.py dto/preview_dto.py services/preview_service.py services/import_service.py imports fill_redmine.py tests
git commit -m "refactor: run imports from project configuration"
```

---

### Task 11: Вкладки импорта в проекте

**Files:**
- Modify: `gui/import_view.py`
- Modify: `gui/project_view.py`
- Modify: `tests/test_gui_formatting.py` (если нужно)
- Create: `tests/test_import_view_helpers.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `ImportService`, `ImportAction`, `GuiWorker`.
- Produces:
  - `ImportView(parent, project, service, worker, action, event_prefix)`
  - `ImportView.busy -> bool`
  - `ImportView.reload_project(project) -> None` (не обязательно; при смене настроек ProjectView пересоздаётся).

- [ ] **Step 1: Write failing test for action labels**

```python
# tests/test_import_view_helpers.py
from dto.import_action import ImportAction


def test_action_labels_are_human_readable():
    assert ImportAction.REDMINE_FILL.label == "Redmine"
    assert ImportAction.YOUTRACK_TRANSFER.label == "YouTrack → Redmine"


def test_action_values_are_stable():
    assert ImportAction.REDMINE_FILL.value == "redmine_fill"
    assert ImportAction.YOUTRACK_TRANSFER.value == "youtrack_transfer"
```

- [ ] **Step 2: Replace ImportView**

```python
# gui/import_view.py
import asyncio
import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from gui.formatting import format_hours, format_range
from gui.worker import GuiWorker
from services.import_service import (
    ImportService,
    ImportSummary,
    PrepareResult,
    PreparedImport,
)


class ImportView(ttk.LabelFrame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        service: ImportService,
        worker: GuiWorker,
        action: ImportAction,
        event_prefix: str,
    ):
        super().__init__(parent, text=action.label, padding=4)
        self.project = project
        self.service = service
        self.worker = worker
        self.action = action
        self.event_prefix = event_prefix
        self.prepared: list[PreparedImport] = []
        self.busy = False
        self._build()
        self._register_handlers()

    def _kind(self, suffix: str) -> str:
        return f"{self.event_prefix}_{suffix}"

    def _register_handlers(self) -> None:
        self.worker.register(self._kind("log"), self.log)
        self.worker.register(self._kind("preview_done"), self._on_preview_done)
        self.worker.register(self._kind("import_done"), self._on_import_done)
        self.worker.register(self._kind("error"), self._on_worker_error)
        self.worker.register(self._kind("progress"), self._on_progress)

    def _build(self) -> None:
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.preview_button = ttk.Button(
            buttons, text="Построить превью", command=self.build_preview
        )
        self.preview_button.pack(side="left", padx=2)
        self.import_button = ttk.Button(
            buttons,
            text="Запустить импорт",
            command=self.run_import,
            state="disabled",
        )
        self.import_button.pack(side="left", padx=2)

        columns = ("issue", "subject", "periods", "total")
        headings = {
            "issue": ("Issue", 90),
            "subject": ("Тема", 300),
            "periods": ("Периоды", 360),
            "total": ("Всего", 80),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("error", foreground="#c0392b")
        self.tree.pack(fill="both", expand=True, pady=4)

        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", pady=4)
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.StringVar(value="")
        ttk.Label(progress_frame, textvariable=self.progress_label, width=28).pack(
            side="left", padx=6
        )

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.preview_button.configure(state="disabled" if busy else "normal")
        can_import = not busy and bool(self.prepared)
        self.import_button.configure(
            state="normal" if can_import else "disabled"
        )

    def build_preview(self) -> None:
        self.prepared = []
        self.import_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.log("Строю превью...")
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.prepare(self.project, self.action),
            done_kind=self._kind("preview_done"),
            error_kind=self._kind("error"),
        )

    def _on_preview_done(self, result: PrepareResult) -> None:
        try:
            self.prepared = result.items
            for item in result.items:
                preview = item.preview
                parent = self.tree.insert(
                    "",
                    "end",
                    values=(
                        preview.issue_id,
                        preview.issue_subject or "—",
                        "",
                        format_hours(preview.total_hours),
                    ),
                )
                for date_range in preview.ranges:
                    self.tree.insert(
                        parent,
                        "end",
                        values=(
                            "",
                            "",
                            format_range(date_range),
                            format_hours(date_range.hours),
                        ),
                    )
            for preview in result.errors:
                self.tree.insert(
                    "",
                    "end",
                    tags=("error",),
                    values=(
                        preview.issue_id,
                        f"Ошибка: {preview.error}",
                        "",
                        "",
                    ),
                )
            self.log(
                f"Превью готово: записей {sum(len(i.records) for i in result.items)}, "
                f"ошибок {len(result.errors)}"
            )
            if not result.items:
                messagebox.showinfo(
                    "Work Assistant", "Нет записей для импорта", parent=self
                )
        finally:
            self._set_busy(False)

    def run_import(self) -> None:
        if not self.prepared:
            messagebox.showinfo(
                "Work Assistant", "Сначала постройте превью", parent=self
            )
            return
        total = sum(len(item.records) for item in self.prepared)
        if not messagebox.askyesno(
            "Work Assistant",
            f"Импортировать {total} записей в Redmine?",
            parent=self,
        ):
            return
        items = self.prepared
        self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.progress_label.set("")
        self._set_busy(True)

        def progress_cb(completed: int, global_total: int, name: str) -> None:
            self.worker.send(
                self._kind("progress"), (completed, global_total, name)
            )

        self.worker.submit(
            lambda: asyncio.run(
                self.service.run(items, progress_cb=progress_cb)
            ),
            done_kind=self._kind("import_done"),
            error_kind=self._kind("error"),
        )

    def _on_progress(self, payload: tuple[int, int, str]) -> None:
        completed, total, name = payload
        self.progress_bar.configure(value=completed)
        self.progress_label.set(f"{name} {completed}/{total}")

    def _on_import_done(self, summary: ImportSummary) -> None:
        try:
            self.prepared = []
            self.progress_label.set("")
            success = summary.total - len(summary.errors)
            message = (
                f"Импорт завершён: успешно {success}, "
                f"ошибок {len(summary.errors)}"
            )
            self.log(message)
            for project_name, spent_on, error in summary.errors:
                self.log(f"  {project_name} {spent_on}: {error}")
            messagebox.showinfo("Work Assistant", message, parent=self)
        finally:
            self._set_busy(False)

    def _on_worker_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Work Assistant", str(exc), parent=self)
```

- [ ] **Step 3: Wire tabs in ProjectView**

Замените `_build_placeholders` на:

```python
    def _build_placeholders(self) -> None:
        from gui.import_view import ImportView
        from dto.import_action import ImportAction

        self.redmine_view = ImportView(
            self.notebook,
            self.project,
            self.service,
            self.worker,
            ImportAction.REDMINE_FILL,
            "redmine",
        )
        self.notebook.add(self.redmine_view, text="Redmine")

        self.youtrack_view = ImportView(
            self.notebook,
            self.project,
            self.service,
            self.worker,
            ImportAction.YOUTRACK_TRANSFER,
            "youtrack",
        )
        self.notebook.add(self.youtrack_view, text="YouTrack → Redmine")

        placeholder = ttk.Frame(self.notebook, padding=12)
        ttk.Label(
            placeholder,
            text="Вкладка плана по коммитам будет добавлена следующим шагом",
        ).pack()
        self.notebook.add(placeholder, text="Коммиты и план")
```

И `busy`:

```python
    @property
    def busy(self) -> bool:
        return self.redmine_view.busy or self.youtrack_view.busy
```

- [ ] **Step 4: Run tests and compile**

Run: `pytest tests/test_import_view_helpers.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

Run: `python -m py_compile gui/import_view.py gui/project_view.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/import_view.py gui/project_view.py tests/test_import_view_helpers.py
git commit -m "feat: add project import tabs"
```

---

### Task 12: Вкладка «Коммиты и план»

**Files:**
- Create: `gui/commit_plan_view.py`
- Modify: `gui/project_view.py`
- Create: `tests/test_commit_plan_formatting.py`

**Interfaces:**
- Consumes: `GitClient`, `CommitPlanService`, `AiClient`, `resolve_ai_config`, `configured_trackers`, `ProjectRepository`, `GuiWorker`.
- Produces:
  - `CommitPlanView(parent, project, repo, worker)`
  - `CommitPlanView.busy -> bool`
  - `format_plan_text(plan: CommitPlanDTO) -> str`

- [ ] **Step 1: Write failing formatting test**

```python
# tests/test_commit_plan_formatting.py
from dto.commit_plan_dto import CommitPlanDTO, DayPlanDTO
from gui.commit_plan_view import format_plan_text


def test_format_plan_text_contains_days_and_summary():
    plan = CommitPlanDTO(
        summary="Итог",
        days=[
            DayPlanDTO(
                date="2026-10-01",
                existing_hours=3,
                deficit_hours=5,
                planned_hours=4,
                comment="Импорт",
                commit_hashes=["aaa111"],
                confidence="high",
            )
        ],
    )

    text = format_plan_text(plan)

    assert "Итог" in text
    assert "2026-10-01" in text
    assert "4h" in text
    assert "Импорт" in text
```

- [ ] **Step 2: Implement the view**

```python
# gui/commit_plan_view.py
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from clients.ai_client import AiClient, resolve_ai_config
from clients.git_client import GitClient
from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO
from gui.project_validation import parse_period
from gui.worker import GuiWorker
from services.commit_plan_service import CommitPlanService
from storage.project_repository import ProjectRepository
from trackers.registry import configured_trackers


def format_plan_text(plan: CommitPlanDTO) -> str:
    lines: list[str] = []
    if plan.summary:
        lines.append(plan.summary)
        lines.append("")
    for day in plan.days:
        if day.planned_hours <= 0:
            continue
        lines.append(
            f"{day.date} — {day.planned_hours:g}h — {day.comment}"
        )
        if day.commit_hashes:
            lines.append(f"  commits: {', '.join(day.commit_hashes)}")
    if not lines:
        return "Нет предложений по часам."
    return "\n".join(lines)


class CommitPlanView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        worker: GuiWorker,
    ):
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.worker = worker
        self.commits = []
        self.plan: CommitPlanDTO | None = None
        self.busy = False
        self.tracker_vars: dict[str, tk.BooleanVar] = {}
        self._build()
        self._register_handlers()

    def _kind(self, suffix: str) -> str:
        return f"plan_{suffix}"

    def _register_handlers(self) -> None:
        self.worker.register(self._kind("commits_done"), self._on_commits_done)
        self.worker.register(self._kind("plan_done"), self._on_plan_done)
        self.worker.register(self._kind("error"), self._on_error)

    def _build(self) -> None:
        period = ttk.Frame(self)
        period.pack(fill="x")
        ttk.Label(period, text="С").pack(side="left")
        self.start_var = ttk.Entry(period, width=12)
        self.start_var.pack(side="left", padx=4)
        self.start_var.insert(0, date.today().replace(day=1).isoformat())
        ttk.Label(period, text="По").pack(side="left")
        self.end_var = ttk.Entry(period, width=12)
        self.end_var.pack(side="left", padx=4)
        self.end_var.insert(0, date.today().isoformat())
        self.load_button = ttk.Button(
            period, text="Загрузить коммиты", command=self.load_commits
        )
        self.load_button.pack(side="left", padx=8)

        self.commit_tree = ttk.Treeview(
            self,
            columns=("date", "hash", "subject"),
            show="headings",
            height=8,
        )
        for column, (title, width) in {
            "date": ("Дата", 130),
            "hash": ("Хеш", 90),
            "subject": ("Тема", 600),
        }.items():
            self.commit_tree.heading(column, text=title)
            self.commit_tree.column(column, width=width, anchor="w")
        self.commit_tree.pack(fill="both", expand=True, pady=6)

        trackers_frame = ttk.LabelFrame(
            self, text="Учитывать уже затреканные часы", padding=6
        )
        trackers_frame.pack(fill="x", pady=4)
        configured = configured_trackers(self.project)
        selected = self.project.ai.get("selected_trackers", [])
        if not isinstance(selected, list):
            selected = []
        default_kind = (
            "youtrack"
            if any(tracker.kind == "youtrack" for tracker in configured)
            else (configured[0].kind if configured else "")
        )
        for tracker in configured:
            variable = tk.BooleanVar(
                value=(
                    tracker.kind in selected
                    if selected
                    else tracker.kind == default_kind
                )
            )
            self.tracker_vars[tracker.kind] = variable
            ttk.Checkbutton(
                trackers_frame,
                text=tracker.label,
                variable=variable,
            ).pack(side="left", padx=6)
        if not configured:
            ttk.Label(
                trackers_frame,
                text="Настройте хотя бы один трекер в настройках проекта",
            ).pack(anchor="w")

        self.generate_button = ttk.Button(
            self,
            text="Сгенерировать план",
            command=self.generate_plan,
            state="disabled",
        )
        self.generate_button.pack(anchor="w", pady=4)

        ttk.Label(
            self,
            text="В YouTrack ничего не записывается — план нужно вставить вручную.",
            foreground="#777",
        ).pack(anchor="w")

        self.plan_tree = ttk.Treeview(
            self,
            columns=("date", "existing", "deficit", "planned", "comment", "commits"),
            show="headings",
            height=10,
        )
        for column, (title, width) in {
            "date": ("Дата", 100),
            "existing": ("Было", 70),
            "deficit": ("Дефицит", 80),
            "planned": ("Предложено", 90),
            "comment": ("Комментарий", 360),
            "commits": ("Коммиты", 160),
        }.items():
            self.plan_tree.heading(column, text=title)
            self.plan_tree.column(column, width=width, anchor="w")
        self.plan_tree.pack(fill="both", expand=True, pady=6)

        self.summary_text = ttk.Label(self, text="", wraplength=900)
        self.summary_text.pack(anchor="w")
        self.copy_button = ttk.Button(
            self, text="Копировать план", command=self.copy_plan, state="disabled"
        )
        self.copy_button.pack(anchor="w", pady=4)

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=5, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.load_button.configure(state="disabled" if busy else "normal")
        can_generate = (
            not busy
            and bool(self.commits)
            and any(variable.get() for variable in self.tracker_vars.values())
        )
        self.generate_button.configure(
            state="normal" if can_generate else "disabled"
        )

    def load_commits(self) -> None:
        try:
            start, end = parse_period(self.start_var.get(), self.end_var.get())
        except ValueError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        self.log(f"Загружаю коммиты за {start.isoformat()} — {end.isoformat()}")
        self._set_busy(True)
        client = GitClient(self.project.git_repo_path)
        self.worker.submit(
            lambda: client.list_commits(
                self.project.git_author_email, start, end
            ),
            done_kind=self._kind("commits_done"),
            error_kind=self._kind("error"),
        )

    def _on_commits_done(self, commits) -> None:
        self.commits = list(commits)
        self.commit_tree.delete(*self.commit_tree.get_children())
        for commit in self.commits:
            self.commit_tree.insert(
                "",
                "end",
                values=(
                    commit.date[:10],
                    commit.hash[:7],
                    commit.subject,
                ),
            )
        self.log(f"Загружено коммитов: {len(self.commits)}")
        self._set_busy(False)

    def generate_plan(self) -> None:
        try:
            start, end = parse_period(self.start_var.get(), self.end_var.get())
        except ValueError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        selected = [
            kind for kind, variable in self.tracker_vars.items() if variable.get()
        ]
        if not selected:
            messagebox.showinfo(
                "Work Assistant", "Выберите хотя бы один трекер", parent=self
            )
            return

        self.project.ai["selected_trackers"] = selected
        if self.project.db_id is not None:
            self.repo.update_project(self.project.db_id, self.project)

        try:
            ai_client = AiClient(resolve_ai_config(self.project))
        except Exception as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return

        service = CommitPlanService(ai_client=ai_client, log=self.log)
        commits = list(self.commits)
        self.log(f"Генерирую план через {ai_client.config.model}...")
        self._set_busy(True)
        self.worker.submit(
            lambda: service.generate(
                self.project, start, end, selected, commits
            ),
            done_kind=self._kind("plan_done"),
            error_kind=self._kind("error"),
        )

    def _on_plan_done(self, plan: CommitPlanDTO) -> None:
        self.plan = plan
        self.plan_tree.delete(*self.plan_tree.get_children())
        for day in plan.days:
            self.plan_tree.insert(
                "",
                "end",
                values=(
                    day.date,
                    f"{day.existing_hours:g}",
                    f"{day.deficit_hours:g}",
                    f"{day.planned_hours:g}",
                    day.comment,
                    ", ".join(hash[:7] for hash in day.commit_hashes),
                ),
            )
        self.summary_text.configure(text=plan.summary)
        self.copy_button.configure(
            state="normal" if any(day.planned_hours for day in plan.days) else "disabled"
        )
        self.log(f"План готов: дней с предложениями {sum(1 for d in plan.days if d.planned_hours)}")
        self._set_busy(False)

    def copy_plan(self) -> None:
        if self.plan is None:
            return
        text = format_plan_text(self.plan)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Work Assistant", "План скопирован", parent=self)

    def _on_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Work Assistant", str(exc), parent=self)
```

- [ ] **Step 3: Wire the tab**

В `gui/project_view.py` замените placeholder для третьей вкладки на:

```python
        from gui.commit_plan_view import CommitPlanView

        self.commit_plan_view = CommitPlanView(
            self.notebook,
            self.project,
            self.repo,
            self.worker,
        )
        self.notebook.add(self.commit_plan_view, text="Коммиты и план")
```

И `busy`:

```python
    @property
    def busy(self) -> bool:
        return (
            self.redmine_view.busy
            or self.youtrack_view.busy
            or self.commit_plan_view.busy
        )
```

- [ ] **Step 4: Run tests and compile**

Run: `pytest tests/test_commit_plan_formatting.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

Run: `python -m py_compile gui/commit_plan_view.py gui/project_view.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add gui/commit_plan_view.py gui/project_view.py tests/test_commit_plan_formatting.py
git commit -m "feat: add commits and AI plan tab"
```

---

### Task 13: Переименование, CLI, ярлык, README и финальная проверка

**Files:**
- Create: `work_assistant.py`
- Create: `work_assistant_cli.py`
- Create: `tests/test_work_assistant_cli.py`
- Modify: `fill_redmine_gui.py` (тонкая обёртка)
- Modify: `fill_redmine.py` (тонкая обёртка)
- Rename: `Fill Redmine.desktop` → `Work Assistant.desktop`
- Rename: `assets/fill_redmine.svg` → `assets/work_assistant.svg`
- Delete: `gui/user_list_view.py`
- Delete: `gui/user_editor.py`
- Modify: `run_gui.sh`
- Modify: `scripts/install_desktop.sh`
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `MainWindow`, `ProjectRepository`, `migrate_*`, CLI-функции из Task 10.
- Produces:
  - `work_assistant.py` — GUI entry.
  - `work_assistant_cli.py` — CLI entry.
  - legacy-обёртки без поломки старых ярлыков.

- [ ] **Step 1: Write failing CLI test**

```python
# tests/test_work_assistant_cli.py
from unittest.mock import MagicMock, patch

import pytest

from configs.project_config import ProjectConfig
from dto.date_hours_dto import DateHoursDTO
from dto.import_action import ImportAction
from work_assistant_cli import main


def make_project() -> ProjectConfig:
    return ProjectConfig(
        name="Test Project",
        db_id=1,
        trackers={
            "redmine": {
                "api_key": "key",
                "user_id": 1,
                "activity_id": 9,
                "issue_id": 123,
                "comment": "test",
            }
        },
    )


@pytest.mark.asyncio
async def test_main_lists_projects_when_no_id(capsys):
    repo = MagicMock()
    repo.list_projects.return_value = [make_project()]

    await main(repo=repo)

    output = capsys.readouterr().out
    assert "1: Test Project" in output


@pytest.mark.asyncio
async def test_main_runs_import_for_project(capsys):
    importer = MagicMock()
    importer.create_record_list.return_value = [
        DateHoursDTO(date="2026-10-01", hours=8)
    ]
    importer.handle.return_value = []
    repo = MagicMock()
    repo.get_project.return_value = make_project()

    with patch(
        "services.import_service.create_importer", return_value=importer
    ), patch(
        "services.import_service.PreviewService.get_issue_info",
        return_value=None,
    ), patch("builtins.input", return_value="y"):
        await main(
            project_id=1,
            action=ImportAction.REDMINE_FILL,
            repo=repo,
        )

    output = capsys.readouterr().out
    assert "=== Project: Test Project ===" in output
    assert "Import finished" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_work_assistant_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'work_assistant_cli'`.

- [ ] **Step 3: Create CLI module**

```python
# work_assistant_cli.py
import argparse
import asyncio

from dto.import_action import ImportAction
from services.import_service import ImportService
from services.preview_service import PreviewService
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


async def main(
    project_id: int | None = None,
    action: ImportAction = ImportAction.REDMINE_FILL,
    override_issue_id: int | None = None,
    repo: ProjectRepository | None = None,
) -> None:
    repository = repo if repo is not None else ProjectRepository()
    if project_id is None:
        projects = repository.list_projects()
        if not projects:
            print("No projects found.")
            return
        for project in projects:
            print(f"{project.db_id}: {project.name}")
        return

    project = repository.get_project(project_id)
    if project is None:
        print(f"Project {project_id} not found.")
        return
    if override_issue_id:
        config = dict(project.trackers.get("redmine", {}))
        config["issue_id"] = override_issue_id
        project.trackers["redmine"] = config

    PreviewService.print_header()
    service = ImportService()
    result = service.prepare(project, action)

    for item in result.items:
        PreviewService.print_preview(item.preview)
    for preview in result.errors:
        PreviewService.print_preview(preview)

    if not result.items:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")
    summary = await service.run(result.items)
    success = summary.total - len(summary.errors)
    print(f"Import finished: {success} entries, {len(summary.errors)} errors.")


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=int, help="Project ID")
    parser.add_argument(
        "--action",
        choices=[action.value for action in ImportAction],
        default=ImportAction.REDMINE_FILL.value,
    )
    parser.add_argument("--id", type=int, help="Override Redmine issue ID")
    args = parser.parse_args()

    migrate_default_legacy_database()
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo)
    migrate_users_to_projects(project_repo, user_repo)
    asyncio.run(
        main(
            project_id=args.project,
            action=ImportAction(args.action),
            override_issue_id=args.id,
            repo=project_repo,
        )
    )


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Create GUI entry and wrappers**

```python
# work_assistant.py
from gui.app import MainWindow
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


def main() -> None:
    migrate_default_legacy_database(log=print)
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo, log=print)
    migrate_users_to_projects(project_repo, user_repo, log=print)
    app = MainWindow(project_repo)
    app.mainloop()


if __name__ == "__main__":
    main()
```

```python
# fill_redmine_gui.py
from work_assistant import main


if __name__ == "__main__":
    main()
```

```python
# fill_redmine.py
import sys

from work_assistant_cli import cli, main


if __name__ == "__main__":
    print(
        "fill_redmine.py переименован в work_assistant_cli.py",
        file=sys.stderr,
    )
    cli()
```

- [ ] **Step 5: Rename desktop and asset, update launchers**

```bash
git mv "Fill Redmine.desktop" "Work Assistant.desktop"
git mv assets/fill_redmine.svg assets/work_assistant.svg
git rm gui/user_list_view.py gui/user_editor.py
```

`Work Assistant.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=Work Assistant
Comment=Проекты, трекеры и план по коммитам
Exec=/home/oleg/code/fill_redmine/run_gui.sh
Path=/home/oleg/code/fill_redmine
Icon=/home/oleg/code/fill_redmine/assets/work_assistant.svg
Terminal=false
Categories=Utility;
StartupNotify=true
```

`run_gui.sh`: замените последнюю строку на:

```bash
exec "$PYTHON" "$SCRIPT_DIR/work_assistant.py"
```

`scripts/install_desktop.sh` полностью:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ID="work-assistant"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"
OLD_DESKTOP_FILE="$DESKTOP_DIR/fill-redmine-gui.desktop"

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "tkinter не найден. Установите: sudo pacman -S tk"
    exit 1
fi

chmod +x "$PROJECT_DIR/run_gui.sh"
mkdir -p "$DESKTOP_DIR"
rm -f "$OLD_DESKTOP_FILE"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Work Assistant
Comment=Проекты, трекеры и план по коммитам
Exec="$PROJECT_DIR/run_gui.sh"
Path=$PROJECT_DIR
Icon=$PROJECT_DIR/assets/work_assistant.svg
Terminal=false
Categories=Utility;Office;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

if ! command -v qdbus6 >/dev/null 2>&1; then
    echo "Ярлык установлен. qdbus6 не найден: закрепите вручную (ПКМ → Закрепить на панели)."
    exit 0
fi

JS="$(cat <<'JSEOF'
var allPanels = panels();
var pinned = false;
for (var i = 0; i < allPanels.length; i++) {
    var widgets = allPanels[i].widgets();
    for (var j = 0; j < widgets.length; j++) {
        var w = widgets[j];
        if (w.type === "org.kde.plasma.icontasks" || w.type === "org.kde.plasma.taskmanager") {
            w.currentConfigGroup = ["General"];
            var raw = w.readConfig("launchers", "");
            var items = raw.length > 0 ? raw.split(",") : [];
            var entry = "applications:work-assistant.desktop";
            if (items.indexOf(entry) === -1) {
                items.push(entry);
                w.writeConfig("launchers", items.join(","));
                w.reloadConfig();
            }
            pinned = true;
        }
    }
}
print(pinned ? "pinned" : "no-taskmanager");
JSEOF
)"

RESULT="$(qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$JS" 2>/dev/null || true)"

if [[ "$RESULT" == *pinned* ]]; then
    echo "Ярлык установлен и закреплён на панели."
else
    echo "Ярлык установлен. Автопин не удался: закрепите вручную (ПКМ → Закрепить на панели)."
fi
```

- [ ] **Step 6: Update .env.example, .gitignore and README**

`.env.example`:

```dotenv
REDMINE_BASE_URL=https://redmine.org
YOUTRACK_BASE_URL=https://youtrack.cloud
WORK_ASSISTANT_DB=
OPENAI_BASE_URL=
OPENAI_MODEL=
OPENAI_API_KEY=
```

`.gitignore`:

```gitignore
.env
.idea
venv
__pycache__/
user_list.py
user_list.py.migrated
fill_redmine.db
work_assistant.db
configs/__pycache__/
dto/__pycache__/
imports/__pycache__/
.superpowers/
```

`README.md` переписать:

````markdown
# Work Assistant

Проекты для учёта времени: Redmine, YouTrack и ИИ-план по git-коммитам.

## Установка

```bash
sudo pacman -S tk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполните `REDMINE_BASE_URL` и `YOUTRACK_BASE_URL`.

## Запуск

```bash
python work_assistant.py
```

При первом запуске старый `fill_redmine.db` автоматически переименовывается
в `work_assistant.db`, а юзеры из старой таблицы один раз становятся проектами.

## Проекты

Кнопка `+` создаёт проект. У проекта есть:

- Redmine: API key, user_id, activity_id, issue_id, комментарий;
- YouTrack: access token;
- git: путь к локальному репозиторию и email автора;
- ИИ: base_url, model, api_key или env `OPENAI_BASE_URL`, `OPENAI_MODEL`,
  `OPENAI_API_KEY`;
- исключённые даты и рабочий день (по умолчанию 8 часов).

Внутри проекта:

1. **Redmine** — заполняет будни текущего месяца до 8 часов, кроме исключённых
   дат и уже затреканных.
2. **YouTrack → Redmine** — переносит work items текущего месяца в Redmine.
3. **Коммиты и план** — читает коммиты автора по всем веткам, считает дефицит
   часов по выбранным трекерам и просит ИИ предложить план. В YouTrack ничего
   не записывается: план копируется вручную.

## Новый трекер

1. Создайте `trackers/<kind>.py` с классом-наследником `BaseTracker`.
2. Опишите `fields` и реализуйте `get_worklogs(start, end)`.
3. Добавьте импорт класса в `trackers/__init__.py`.

GUI сам покажет поля в настройках проекта и чекбокс на вкладке плана.
Миграции БД не нужны.

## CLI

```bash
python work_assistant_cli.py
python work_assistant_cli.py --project 1 --action youtrack_transfer
```

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```
````

- [ ] **Step 7: Run tests and final checks**

Run: `pytest tests/test_work_assistant_cli.py -q`
Expected: PASS.

Run: `pytest -q`
Expected: PASS.

Run: `python -m py_compile work_assistant.py work_assistant_cli.py fill_redmine.py fill_redmine_gui.py`
Expected: exit 0.

Run: `python work_assistant_cli.py --help`
Expected: usage с `--project`, `--action`, `--id`.

- [ ] **Step 8: Commit**

```bash
git add work_assistant.py work_assistant_cli.py fill_redmine.py fill_redmine_gui.py "Work Assistant.desktop" assets/work_assistant.svg run_gui.sh scripts/install_desktop.sh .gitignore .env.example README.md tests/test_work_assistant_cli.py
git commit -m "feat: rename app to Work Assistant and update launchers"
```

---

## Self-Review

**Spec coverage:**

- Проекты и `+`: Task 1, Task 9.
- Сохранение между сессиями: Task 1.
- Вход в проект: Task 9.
- Redmine старая логика: Task 10, Task 11.
- YouTrack → Redmine: Task 10, Task 11.
- Коммиты по всем веткам: Task 6, Task 12.
- ИИ-план до 8 часов: Task 7, Task 8, Task 12.
- Список трекеров с галочками: Task 3, Task 12.
- Расширяемость трекеров: Task 3, Task 4, Task 5, README в Task 13.
- Только предложение, без записи в YouTrack: Task 12.
- Миграция старых юзеров и БД: Task 1, Task 2.
- Переименование: Task 13.
- Тесты: каждая задача.

**Type consistency:**

- `ProjectConfig.trackers: dict[str, dict]` используется во всех задачах.
- `ImportAction` импортируется из `dto.import_action` везде.
- `PreviewDTO.project_name/action` заменяют `user_name/driver` начиная с Task 10.
- `WorklogDTO` создаётся в Task 3 и используется в Task 4, 5, 8.
- `CommitPlanDTO.days` и `DayPlanDTO` создаются в Task 8 и используются в Task 12.
- `GitCommitDTO` создаётся в Task 6 и используется в Task 8, 12.
- `BaseTracker.validate_config` создаётся в Task 3 и используется в Task 9.
