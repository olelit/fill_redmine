# GUI + SQLite Users Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить Tkinter-GUI для управления юзерами и запуска импорта, перенеся хранение юзеров в SQLite, с установкой ярлыка на панель KDE.

**Architecture:** Слоистый рефакторинг: `gui → services → storage/clients`. SQLite — единый источник правды для GUI и CLI; `ImportService` инкапсулирует превью и импорт с callback-прогрессом; GUI работает с сервисами в фоновом потоке через очередь.

**Tech Stack:** Python 3.14, Tkinter/ttk (системный пакет `tk`), sqlite3 (stdlib), pytest + pytest-asyncio, Bash + `.desktop` + qdbus6 (Plasma 6).

**Spec:** `docs/superpowers/specs/2026-10-06-gui-sqlite-users-design.md`

## Global Constraints

- Python 3.14, только абсолютные импорты, type hints везде.
- Без комментариев в коде.
- Длина строки до 100 символов, 4 пробела.
- БД: `fill_redmine.db` в корне проекта (переопределяется `FILL_REDMINE_DB`), права `600`, файл в `.gitignore`.
- GUI-тексты: русские подписи, технические термины (`driver`, `issue_id`, `user_id`, `activity_id`) как в коде.
- Секреты в SQLite хранятся открытым текстом, в UI маскируются.
- Существующие тесты должны оставаться зелёными после каждой задачи.
- venv проекта: `.venv`; все команды запускать как `.venv/bin/python -m ...`.
- Системная зависимость GUI: `tk` (`sudo pacman -S tk`); pytest ставится в venv.
- Ручные шаги GUI выполняет пользователь; агент проверяет минимум `compileall` и тесты.

---

### Task 1: Слой SQLite (database + user repository)

**Files:**
- Create: `storage/database.py`
- Create: `storage/user_repository.py`
- Create: `requirements-dev.txt`
- Test: `tests/test_user_repository.py`

**Interfaces:**
- Consumes: `UserConfig` из `configs/user_config.py` (существующий; `db_id` добавится в Task 3 — repository уже сейчас принимает/возвращает его через `getattr`, но фактическое поле появится в Task 3; в Task 1 передавать `db_id` нельзя, поэтому `update_user` строится на отдельном параметре).

  ВАЖНО: чтобы Task 1 не зависел от Task 3, `UserConfig` в Task 1 используется как есть (без `db_id`). Repository хранит `id` и возвращает юзеров с `db_id` только начиная с Task 3. В Task 1 `update_user` принимает `db_id` первым аргументом.

- Produces:
  - `storage/database.py`: `SCHEMA: str`, `get_default_db_path() -> Path`, `get_connection(db_path=None) -> sqlite3.Connection`, `create_schema(conn) -> None`.
  - `storage/user_repository.py`: `UserRepository(db_path=None)`; `list_users() -> list[UserConfig]`; `get_user(db_id: int) -> UserConfig | None`; `add_user(user: UserConfig) -> int`; `update_user(db_id: int, user: UserConfig) -> None`; `delete_user(db_id: int) -> None`; `set_enabled(db_id: int, enabled: bool) -> None`.

- [ ] **Step 1: Создать requirements-dev.txt и установить pytest**

`requirements-dev.txt`:

```
pytest
pytest-asyncio
```

Команды:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest --version
```

Expected: `pytest 8.x` (или новее) без ошибок.

- [ ] **Step 2: Прогнать существующие тесты (базовая линия)**

Run: `.venv/bin/python -m pytest -q`
Expected: все существующие тесты PASS. Если падают — остановиться и починить до продолжения.

- [ ] **Step 3: Написать падающий тест репозитория**

`tests/test_user_repository.py`:

```python
from unittest.mock import MagicMock

import pytest

from configs.user_config import MANUAL, UserConfig
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
        exclude_dates=["2026-10-01"],
    )
    data.update(overrides)
    return UserConfig(**data)


@pytest.fixture
def repo(tmp_path):
    return UserRepository(db_path=tmp_path / "test.db")


class TestUserRepository:
    def test_list_users_returns_empty_for_new_db(self, repo):
        assert repo.list_users() == []

    def test_add_and_list_users_roundtrip(self, repo):
        db_id = repo.add_user(make_user())

        users = repo.list_users()

        assert len(users) == 1
        assert db_id == 1
        assert users[0].name == "Олег"
        assert users[0].is_enable is True
        assert users[0].driver == "youtrack"
        assert users[0].exclude_dates == ["2026-10-01"]
        assert users[0].is_youtrack() is True

    def test_get_user_returns_none_for_missing(self, repo):
        assert repo.get_user(999) is None

    def test_update_user_changes_fields(self, repo):
        db_id = repo.add_user(make_user())

        repo.update_user(db_id, make_user(name="Новое имя", is_enable=False))

        user = repo.get_user(db_id)
        assert user.name == "Новое имя"
        assert user.is_enable is False

    def test_update_user_for_missing_id_raises(self, repo):
        with pytest.raises(ValueError):
            repo.update_user(999, make_user())

    def test_delete_user(self, repo):
        db_id = repo.add_user(make_user())

        repo.delete_user(db_id)

        assert repo.list_users() == []

    def test_set_enabled_toggles_flag(self, repo):
        db_id = repo.add_user(make_user())

        repo.set_enabled(db_id, False)
        assert repo.get_user(db_id).is_enable is False

        repo.set_enabled(db_id, True)
        assert repo.get_user(db_id).is_enable is True
```

- [ ] **Step 4: Запустить тест — должен упасть**

Run: `.venv/bin/python -m pytest tests/test_user_repository.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'storage'`.

- [ ] **Step 5: Создать storage/database.py**

`storage/database.py`:

```python
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
```

- [ ] **Step 6: Создать storage/user_repository.py**

`storage/user_repository.py`:

```python
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
    def __init__(self, db_path: Path | str | None = None):
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
        )
```

- [ ] **Step 7: Запустить тесты — должны пройти**

Run: `.venv/bin/python -m pytest tests/test_user_repository.py -q`
Expected: 7 passed.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

- [ ] **Step 8: Коммит**

```bash
git add requirements-dev.txt storage/database.py storage/user_repository.py tests/test_user_repository.py
git commit -m "Add SQLite storage layer for users"
```

---

### Task 2: Миграция из user_list.py

**Files:**
- Create: `storage/migration.py`
- Modify: `.gitignore` (добавить `fill_redmine.db`, `user_list.py.migrated`)
- Test: `tests/test_migration.py`

**Interfaces:**
- Consumes: `UserRepository.list_users()`, `UserRepository.add_user(user)` из Task 1.
- Produces: `storage/migration.py`: `DEFAULT_USER_LIST_PATH: Path`, `migrate_from_user_list(repo, user_list_path=None, log=print) -> bool`.

- [ ] **Step 1: Написать падающие тесты миграции**

`tests/test_migration.py`:

```python
from configs.user_config import MANUAL, UserConfig
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository

USER_LIST_TEMPLATE = '''
from configs.user_config import UserConfig


USERS = [
    UserConfig(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver="youtrack",
        youtrack_access_token="token",
        exclude_dates=[],
    ),
]
'''


def existing_user() -> UserConfig:
    return UserConfig(
        is_enable=True,
        name="Existing",
        redmine_api_key="",
        user_id=1,
        activity_id=1,
        comment="",
        issue_id=1,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
    )


class TestMigrateFromUserList:
    def test_migrates_users_and_renames_file(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        user_list = tmp_path / "user_list.py"
        user_list.write_text(USER_LIST_TEMPLATE)

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is True
        users = repo.list_users()
        assert len(users) == 1
        assert users[0].name == "Олег"
        assert users[0].is_youtrack() is True
        assert not user_list.exists()
        assert (tmp_path / "user_list.py.migrated").exists()

    def test_skips_when_database_not_empty(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        repo.add_user(existing_user())
        user_list = tmp_path / "user_list.py"
        user_list.write_text(USER_LIST_TEMPLATE)

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is False
        assert len(repo.list_users()) == 1
        assert user_list.exists()

    def test_returns_false_when_file_missing(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")

        result = migrate_from_user_list(
            repo, user_list_path=tmp_path / "missing.py", log=lambda message: None
        )

        assert result is False

    def test_broken_file_does_not_raise(self, tmp_path):
        repo = UserRepository(db_path=tmp_path / "test.db")
        user_list = tmp_path / "user_list.py"
        user_list.write_text("raise RuntimeError('boom')")

        result = migrate_from_user_list(repo, user_list_path=user_list, log=lambda message: None)

        assert result is False
        assert repo.list_users() == []
        assert user_list.exists()
```

- [ ] **Step 2: Запустить тесты — должны упасть**

Run: `.venv/bin/python -m pytest tests/test_migration.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'storage.migration'`.

- [ ] **Step 3: Создать storage/migration.py**

`storage/migration.py`:

```python
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
```

- [ ] **Step 4: Запустить тесты — должны пройти**

Run: `.venv/bin/python -m pytest tests/test_migration.py -q`
Expected: 4 passed.

- [ ] **Step 5: Обновить .gitignore**

Новое содержимое `.gitignore`:

```
.env
.idea
venv
__pycache__/
user_list.py
user_list.py.migrated
fill_redmine.db
configs/__pycache__/
dto/__pycache__/
imports/__pycache__/
```

- [ ] **Step 6: Полный прогон и коммит**

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

```bash
git add storage/migration.py tests/test_migration.py .gitignore
git commit -m "Add one-time migration from user_list.py to SQLite"
```

---

### Task 3: PreviewDTO, db_id и build_user_preview

**Files:**
- Create: `dto/preview_dto.py`
- Modify: `configs/user_config.py` (поле `db_id`)
- Modify: `storage/user_repository.py` (возвращать `db_id` в `_row_to_user`)
- Modify: `services/preview_service.py` (новые методы; совместимость со старым CLI)
- Test: `tests/test_preview_service.py`
- Test: `tests/test_user_repository.py` (добавить проверку `db_id`)

**Interfaces:**
- Consumes: `UserConfig`, `DateHoursDTO`, `IssueInfoDTO`.
- Produces:
  - `dto/preview_dto.py`: `DateRangeDTO(start_date: str, end_date: str, hours: int | float)`, `PreviewDTO(user_name, user_id, driver, comment, issue_id, issue_subject, issue_url, issue_author, issue_created_on, ranges, total_hours, error)`.
  - `configs/user_config.py`: `UserConfig.db_id: int | None = None`.
  - `storage/user_repository.py`: `_row_to_user` заполняет `db_id=row["id"]`, чтобы GUI мог адресовать запись для edit/delete.
  - `PreviewService.build_user_preview(user, records, issue_info) -> PreviewDTO`; `PreviewService.print_preview(preview: PreviewDTO) -> None`.

- [ ] **Step 1: Написать падающие тесты превью**

`tests/test_preview_service.py`:

```python
from configs.user_config import MANUAL, YOUTRACK, UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.preview_service import PreviewService


def make_user(**overrides) -> UserConfig:
    data = dict(
        is_enable=True,
        name="Олег",
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
    )
    data.update(overrides)
    return UserConfig(**data)


def make_issue_info() -> IssueInfoDTO:
    return IssueInfoDTO(
        subject="Тема задачи",
        url="http://redmine/issues/2682",
        author="Oleg",
        created_on="2026-10-01 10:00:00 UTC",
    )


class TestBuildUserPreview:
    def test_groups_consecutive_days_with_equal_hours(self):
        records = [
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=8),
            DateHoursDTO(date="2026-10-05", hours=4),
        ]

        preview = PreviewService.build_user_preview(make_user(), records, make_issue_info())

        assert [(r.start_date, r.end_date, r.hours) for r in preview.ranges] == [
            ("2026-10-01", "2026-10-02", 8),
            ("2026-10-05", "2026-10-05", 4),
        ]
        assert preview.total_hours == 20

    def test_splits_range_when_hours_differ(self):
        records = [
            DateHoursDTO(date="2026-10-01", hours=8),
            DateHoursDTO(date="2026-10-02", hours=4),
        ]

        preview = PreviewService.build_user_preview(make_user(), records, None)

        assert [(r.start_date, r.end_date) for r in preview.ranges] == [
            ("2026-10-01", "2026-10-01"),
            ("2026-10-02", "2026-10-02"),
        ]

    def test_empty_records_produce_empty_preview(self):
        preview = PreviewService.build_user_preview(make_user(), [], None)

        assert preview.ranges == []
        assert preview.total_hours == 0

    def test_copies_user_and_issue_fields(self):
        records = [DateHoursDTO(date="2026-10-01", hours=8)]

        preview = PreviewService.build_user_preview(
            make_user(driver=YOUTRACK, comment="fix"), records, make_issue_info()
        )

        assert preview.user_name == "Олег"
        assert preview.user_id == 16
        assert preview.driver == YOUTRACK
        assert preview.comment == "fix"
        assert preview.issue_id == 2682
        assert preview.issue_subject == "Тема задачи"
        assert preview.issue_url == "http://redmine/issues/2682"
        assert preview.issue_author == "Oleg"
        assert preview.issue_created_on == "2026-10-01 10:00:00 UTC"

    def test_missing_issue_info_keeps_none_fields(self):
        preview = PreviewService.build_user_preview(
            make_user(), [DateHoursDTO(date="2026-10-01", hours=8)], None
        )

        assert preview.issue_subject is None
        assert preview.issue_url is None
```

- [ ] **Step 2: Запустить — должно упасть**

Run: `.venv/bin/python -m pytest tests/test_preview_service.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'services.preview_service'` для `build_user_preview` (AttributeError) / `dto.preview_dto`.

- [ ] **Step 3: Создать dto/preview_dto.py**

`dto/preview_dto.py`:

```python
from dataclasses import dataclass, field


@dataclass
class DateRangeDTO:
    start_date: str
    end_date: str
    hours: int | float


@dataclass
class PreviewDTO:
    user_name: str
    user_id: int
    driver: str
    comment: str
    issue_id: int
    issue_subject: str | None = None
    issue_url: str | None = None
    issue_author: str | None = None
    issue_created_on: str | None = None
    ranges: list[DateRangeDTO] = field(default_factory=list)
    total_hours: float = 0
    error: str | None = None
```

- [ ] **Step 4: Добавить db_id в UserConfig**

Новое содержимое `configs/user_config.py`:

```python
from dataclasses import dataclass, field


MANUAL = "manual"
YOUTRACK = "youtrack"


@dataclass
class UserConfig:
    is_enable: bool
    name: str
    redmine_api_key: str
    user_id: int
    activity_id: int
    comment: str
    issue_id: int
    driver: str
    youtrack_access_token: str
    exclude_dates: list[str] = field(default_factory=list)
    db_id: int | None = None

    def is_manual(self) -> bool:
        return self.driver == MANUAL

    def is_youtrack(self) -> bool:
        return self.driver == YOUTRACK
```

- [ ] **Step 5: Заполнить db_id в репозитории**

В `storage/user_repository.py` в методе `_row_to_user` добавить последним аргументом:

```python
            db_id=row["id"],
```

Чтобы получилось:

```python
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
```

Добавить тест в `tests/test_user_repository.py` (в класс `TestUserRepository`):

```python
    def test_list_users_populates_db_id(self, repo):
        db_id = repo.add_user(make_user())

        users = repo.list_users()

        assert users[0].db_id == db_id
```

- [ ] **Step 6: Переписать services/preview_service.py**

Новое содержимое `services/preview_service.py`:

```python
from datetime import date

from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import DateRangeDTO, PreviewDTO
from services.issue_service import IssueService


class PreviewService:
    @staticmethod
    def get_issue_info(
        issue_info_cache: dict[int, IssueInfoDTO | None],
        user: UserConfig,
    ) -> IssueInfoDTO | None:
        if user.issue_id not in issue_info_cache:
            issue_info_cache[user.issue_id] = IssueService.get_issue_info(
                issue_id=user.issue_id,
                api_key=user.redmine_api_key,
            )

        return issue_info_cache[user.issue_id]

    @staticmethod
    def build_user_preview(
        user: UserConfig,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
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

        return PreviewDTO(
            user_name=user.name,
            user_id=user.user_id,
            driver=user.driver,
            comment=user.comment,
            issue_id=user.issue_id,
            issue_subject=issue_info.subject if issue_info else None,
            issue_url=issue_info.url if issue_info else None,
            issue_author=issue_info.author if issue_info else None,
            issue_created_on=issue_info.created_on if issue_info else None,
            ranges=ranges,
            total_hours=total_hours,
        )

    @staticmethod
    def print_header() -> None:
        print("\n" + "=" * 50)
        print("Time entries to be imported")
        print("=" * 50 + "\n")

    @staticmethod
    def print_preview(preview: PreviewDTO) -> None:
        print(f"=== User: {preview.user_name} (user_id={preview.user_id}) ===")
        if preview.issue_subject is None:
            print(f"Issue Data: {preview.issue_id}")
        else:
            print(
                f"Issue Data: Id: {preview.issue_id}, "
                f"Author: {preview.issue_author}, Created: {preview.issue_created_on}"
            )
            print(f"Issue: {preview.issue_subject}")
            print(f"Issue URL: {preview.issue_url}")
        print(f"Driver: {preview.driver}")
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

    @staticmethod
    def print_user_preview(
        user: UserConfig,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
    ) -> None:
        preview = PreviewService.build_user_preview(user, records, issue_info)
        PreviewService.print_preview(preview)
```

- [ ] **Step 7: Запустить новые и все существующие тесты**

Run: `.venv/bin/python -m pytest tests/test_preview_service.py -q`
Expected: 5 passed.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS (старый `print_user_preview` сохранён для совместимости с текущим CLI).

- [ ] **Step 8: Коммит**

```bash
git add dto/preview_dto.py configs/user_config.py storage/user_repository.py services/preview_service.py tests/test_preview_service.py tests/test_user_repository.py
git commit -m "Add PreviewDTO and build_user_preview"
```

---

### Task 4: Прогресс-колбэки и ImportService

**Files:**
- Modify: `clients/redmine_client.py`
- Modify: `imports/base_importer.py`
- Create: `services/import_service.py`
- Test: `tests/test_import_service.py`

**Interfaces:**
- Consumes: `PreviewService.build_user_preview` / `get_issue_info` (Task 3), `create_importer` (существует).
- Produces:
  - `RedmineClient.create_time_entries(..., on_progress: Callable[[int, int], None] | None = None) -> list[tuple[str, str]]`.
  - `BaseImporter.handle(records=None, on_progress=None) -> list[tuple[str, str]]`.
  - `ImportService(log=print)`; `prepare(users) -> list[PreparedImport]`; `run(items, progress_cb=None) -> ImportSummary`.
  - `PreparedImport(user, importer, records, preview)`; `ImportSummary(total, errors)`.

- [ ] **Step 1: Написать падающие тесты ImportService**

`tests/test_import_service.py`:

```python
import pytest

from configs.user_config import MANUAL, UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from services.import_service import ImportService, PreparedImport
from services.preview_service import PreviewService


def make_user(name="Олег") -> UserConfig:
    return UserConfig(
        is_enable=True,
        name=name,
        redmine_api_key="key",
        user_id=16,
        activity_id=9,
        comment="development",
        issue_id=2682,
        driver=MANUAL,
        youtrack_access_token="",
        exclude_dates=[],
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
        self.records = records if records is not None else []
        self.errors = errors if errors is not None else []
        self.create_calls = 0
        self.handle_calls = []

    def create_record_list(self):
        self.create_calls += 1
        return self.records

    async def handle(self, records=None, on_progress=None):
        self.handle_calls.append(records)
        if on_progress is not None:
            for completed in range(1, len(records) + 1):
                on_progress(completed, len(records))
        return list(self.errors)


class TestImportServicePrepare:
    def test_prepare_builds_preview_without_refetching_records(self, monkeypatch):
        service = ImportService(log=lambda message: None)
        records = [DateHoursDTO(date="2026-10-01", hours=8)]
        importer = FakeImporter(records=records)
        monkeypatch.setattr("services.import_service.create_importer", lambda user: importer)
        monkeypatch.setattr(
            "services.import_service.PreviewService.get_issue_info",
            lambda issue_info_cache, user: make_issue_info(),
        )

        items = service.prepare([make_user()])

        assert len(items) == 1
        assert importer.create_calls == 1
        assert items[0].preview.user_name == "Олег"
        assert items[0].preview.issue_subject == "Тема"
        assert items[0].records == records

    def test_prepare_skips_user_when_importer_missing(self, monkeypatch):
        logs = []
        service = ImportService(log=logs.append)
        monkeypatch.setattr("services.import_service.create_importer", lambda user: None)

        items = service.prepare([make_user()])

        assert items == []
        assert any("driver" in message for message in logs)

    def test_prepare_skips_user_without_records(self, monkeypatch):
        service = ImportService(log=lambda message: None)
        importer = FakeImporter(records=[])
        monkeypatch.setattr("services.import_service.create_importer", lambda user: importer)

        assert service.prepare([make_user()]) == []
        assert importer.create_calls == 1

    def test_prepare_logs_and_skips_fetch_errors(self, monkeypatch):
        logs = []

        class BrokenImporter:
            def create_record_list(self):
                raise RuntimeError("network down")

        monkeypatch.setattr(
            "services.import_service.create_importer", lambda user: BrokenImporter()
        )

        items = ImportService(log=logs.append).prepare([make_user()])

        assert items == []
        assert any("network down" in message for message in logs)


class TestImportServiceRun:
    @pytest.mark.asyncio
    async def test_run_reports_global_progress_and_collects_errors(self):
        user_one = make_user(name="Первый")
        user_two = make_user(name="Второй")
        importer_one = FakeImporter(
            records=[
                DateHoursDTO(date="2026-10-01", hours=8),
                DateHoursDTO(date="2026-10-02", hours=8),
            ]
        )
        importer_two = FakeImporter(
            records=[DateHoursDTO(date="2026-10-01", hours=4)],
            errors=[("2026-10-01", "500 error")],
        )
        service = ImportService(log=lambda message: None)
        progress = []

        items = [
            PreparedImport(
                user=user_one,
                importer=importer_one,
                records=importer_one.records,
                preview=PreviewService.build_user_preview(user_one, importer_one.records, None),
            ),
            PreparedImport(
                user=user_two,
                importer=importer_two,
                records=importer_two.records,
                preview=PreviewService.build_user_preview(user_two, importer_two.records, None),
            ),
        ]

        summary = await service.run(
            items,
            progress_cb=lambda completed, total, name: progress.append(
                (completed, total, name)
            ),
        )

        assert progress == [(1, 3, "Первый"), (2, 3, "Первый"), (3, 3, "Второй")]
        assert summary.total == 3
        assert summary.errors == [("Второй", "2026-10-01", "500 error")]
        assert importer_one.handle_calls == [importer_one.records]
        assert importer_two.handle_calls == [importer_two.records]

    @pytest.mark.asyncio
    async def test_run_without_items_returns_empty_summary(self):
        summary = await ImportService(log=lambda message: None).run([])

        assert summary.total == 0
        assert summary.errors == []
```

- [ ] **Step 2: Запустить — должно упасть**

Run: `.venv/bin/python -m pytest tests/test_import_service.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'services.import_service'`.

- [ ] **Step 3: Добавить on_progress в RedmineClient**

В `clients/redmine_client.py` добавить импорт:

```python
from collections.abc import Callable
```

Заменить метод `create_time_entries` целиком на:

```python
    async def create_time_entries(
        self,
        user_id: int,
        issue_id: int,
        comment: str,
        activity_id: int,
        records: list[DateHoursDTO],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[tuple[str, str]]:
        url = f"{self.base_url}/time_entries.xml"
        headers = {
            "Content-Type": "application/xml",
            "X-Redmine-API-Key": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            tasks = [
                asyncio.create_task(
                    self.create_time_entry(
                        session=session,
                        url=url,
                        headers=headers,
                        issue_id=issue_id,
                        user_id=user_id,
                        spent_on=record.date,
                        hours=record.hours,
                        activity_id=activity_id,
                        comment=comment,
                    )
                )
                for record in records
            ]

            total = len(tasks)
            if total == 0:
                return []

            errors: list[tuple[str, str]] = []
            completed = 0
            if on_progress is None:
                self.print_progress(completed=completed, total=total)

            for task in asyncio.as_completed(tasks):
                success, spent_on, error_message = await task
                completed += 1

                if not success:
                    print()
                    print(f"ERROR: {spent_on} {error_message}")
                    errors.append((spent_on, error_message))

                if on_progress is not None:
                    on_progress(completed, total)
                else:
                    self.print_progress(completed=completed, total=total)

            return errors
```

- [ ] **Step 4: Обновить BaseImporter**

Новое содержимое `imports/base_importer.py`:

```python
from abc import ABC, abstractmethod
from collections.abc import Callable

from clients.redmine_client import RedmineClient
from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO


class BaseImporter(ABC):
    def __init__(self, user: UserConfig):
        self.user = user

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

        return await self.update_redmine_activity(
            self.user.user_id,
            self.user.issue_id,
            self.user.comment,
            self.user.activity_id,
            self.user.redmine_api_key,
            records,
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

- [ ] **Step 5: Создать services/import_service.py**

`services/import_service.py`:

```python
from collections.abc import Callable
from dataclasses import dataclass, field

from configs.user_config import UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from dto.preview_dto import PreviewDTO
from imports.base_importer import BaseImporter
from imports.import_factory import create_importer
from services.preview_service import PreviewService


@dataclass
class PreparedImport:
    user: UserConfig
    importer: BaseImporter
    records: list[DateHoursDTO]
    preview: PreviewDTO


@dataclass
class ImportSummary:
    total: int
    errors: list[tuple[str, str, str]] = field(default_factory=list)


class ImportService:
    def __init__(self, log: Callable[[str], None] = print):
        self.log = log

    def prepare(self, users: list[UserConfig]) -> list[PreparedImport]:
        items: list[PreparedImport] = []
        issue_info_cache: dict[int, IssueInfoDTO | None] = {}

        for user in users:
            importer = create_importer(user)
            if importer is None:
                self.log(f"{user.name}: неизвестный driver «{user.driver}», пропуск")
                continue

            try:
                records = importer.create_record_list()
            except Exception as exc:
                self.log(f"{user.name}: ошибка получения записей: {exc}")
                continue

            if not records:
                self.log(f"{user.name}: нет записей")
                continue

            issue_info = PreviewService.get_issue_info(
                issue_info_cache=issue_info_cache,
                user=user,
            )
            preview = PreviewService.build_user_preview(
                user=user,
                records=records,
                issue_info=issue_info,
            )
            items.append(
                PreparedImport(
                    user=user,
                    importer=importer,
                    records=records,
                    preview=preview,
                )
            )

        return items

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
                name: str = item.user.name,
            ) -> None:
                if progress_cb is not None:
                    progress_cb(base + completed, total, name)

            item_errors = await item.importer.handle(
                records=item.records,
                on_progress=on_progress,
            )
            for spent_on, message in item_errors or []:
                errors.append((item.user.name, spent_on, message))
            completed_base += len(item.records)

        return ImportSummary(total=total, errors=errors)
```

- [ ] **Step 6: Запустить тесты — должны пройти**

Run: `.venv/bin/python -m pytest tests/test_import_service.py -q`
Expected: 6 passed.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

- [ ] **Step 7: Коммит**

```bash
git add clients/redmine_client.py imports/base_importer.py services/import_service.py tests/test_import_service.py
git commit -m "Add ImportService with progress callbacks"
```

---

### Task 5: CLI на репозитории

**Files:**
- Modify: `fill_redmine.py`
- Modify: `services/preview_service.py` (удалить совместимостный `print_user_preview`)
- Test: `tests/test_fill_redmine.py` (обновить)

**Interfaces:**
- Consumes: `UserRepository` (Task 1), `migrate_from_user_list` (Task 2), `ImportService`/`PreparedImport`/`ImportSummary` (Task 4), `PreviewService.print_preview` (Task 3).
- Produces: `main(override_issue_id: int | None = None, repo: UserRepository | None = None) -> None`; CLI `python fill_redmine.py [--id N]`.

- [ ] **Step 1: Переписать fill_redmine.py**

Новое содержимое `fill_redmine.py`:

```python
import argparse
import asyncio

from services.import_service import ImportService
from services.preview_service import PreviewService
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository


async def main(
    override_issue_id: int | None = None,
    repo: UserRepository | None = None,
) -> None:
    repository = repo if repo is not None else UserRepository()
    users = repository.list_users()
    enabled_users = [user for user in users if user.is_enable]
    if not enabled_users:
        print("No enabled users found.")
        return

    if override_issue_id:
        for user in enabled_users:
            user.issue_id = override_issue_id

    PreviewService.print_header()

    service = ImportService()
    items = service.prepare(enabled_users)

    for item in items:
        PreviewService.print_preview(item.preview)

    if not items:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")

    summary = await service.run(items)
    print(f"Import finished: {summary.total} entries, {len(summary.errors)} errors.")


if __name__ == "__main__":
    repository = UserRepository()
    migrate_from_user_list(repository)

    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Override issue ID for all users")
    args = parser.parse_args()
    asyncio.run(main(override_issue_id=args.id, repo=repository))
```

- [ ] **Step 2: Удалить совместимостный print_user_preview**

В `services/preview_service.py` удалить метод:

```python
    @staticmethod
    def print_user_preview(
        user: UserConfig,
        records: list[DateHoursDTO],
        issue_info: IssueInfoDTO | None,
    ) -> None:
        preview = PreviewService.build_user_preview(user, records, issue_info)
        PreviewService.print_preview(preview)
```

- [ ] **Step 3: Обновить тест fill_redmine**

Новое содержимое `tests/test_fill_redmine.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from configs.user_config import MANUAL, UserConfig
from dto.date_hours_dto import DateHoursDTO
from dto.issue_info_dto import IssueInfoDTO
from fill_redmine import main
from services.issue_service import IssueService


class TestFillRedmine:
    def test_format_created_on_formats_iso_datetime(self):
        result = IssueService.format_created_on("2026-03-31T08:13:51Z")

        assert result == "2026-03-31 08:13:51 UTC"

    def test_get_issue_info_returns_subject_author_and_url(self):
        with patch(
            "clients.redmine_client.Config.get_redmine_base_url",
            return_value="http://redmine/",
        ), patch("clients.redmine_client.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "issue": {
                    "subject": "Fill Redmine output",
                    "author": {"name": "Oleg"},
                    "created_on": "2026-03-31T08:13:51Z",
                }
            }
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = IssueService.get_issue_info(issue_id=2574, api_key="test_api_key")

        assert result == IssueInfoDTO(
            subject="Fill Redmine output",
            url="http://redmine/issues/2574",
            author="Oleg",
            created_on="2026-03-31 08:13:51 UTC",
        )

    @pytest.mark.asyncio
    async def test_main_prints_issue_details_before_dates(self, capsys):
        user = UserConfig(
            is_enable=True,
            name="Test User",
            redmine_api_key="test_api_key",
            user_id=1,
            activity_id=9,
            comment="test work",
            issue_id=123,
            driver=MANUAL,
            youtrack_access_token="",
            exclude_dates=[],
        )

        mock_importer = MagicMock()
        mock_importer.create_record_list.return_value = [
            DateHoursDTO(date="2026-03-31", hours=8),
        ]
        mock_importer.handle.return_value = []

        mock_repo = MagicMock()
        mock_repo.list_users.return_value = [user]

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
            await main(repo=mock_repo)

        output = capsys.readouterr().out

        assert "Issue Data: Id: 123, Author: Oleg, Created: 2026-03-30 10:00:00 UTC" in output
        assert "Issue: Issue title" in output
        assert "Issue URL: http://redmine/issues/123" in output
        assert output.index("Issue: Issue title") < output.index("Dates:")
```

- [ ] **Step 4: Прогнать тесты и CLI**

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

Run: `.venv/bin/python fill_redmine.py --help`
Expected: справка с `--id`, без запуска импорта.

- [ ] **Step 5: Коммит**

```bash
git add fill_redmine.py services/preview_service.py tests/test_fill_redmine.py
git commit -m "Switch CLI to SQLite user repository"
```

---

### Task 6: GUI — валидация, диалог юзера, список юзеров

**Files:**
- Create: `gui/validation.py`
- Create: `gui/user_editor.py`
- Create: `gui/user_list_view.py`
- Test: `tests/test_gui_validation.py`

**Interfaces:**
- Consumes: `UserConfig`, `MANUAL`, `YOUTRACK`, `UserRepository`.
- Produces:
  - `gui/validation.py`: `validate_user_form(form: dict[str, str], is_enable: bool, exclude_dates: list[str], db_id: int | None = None) -> tuple[UserConfig | None, list[str]]`; `parse_exclude_date(value: str, existing: list[str]) -> tuple[str | None, str | None]`.
  - `gui/user_editor.py`: `UserEditor(parent, user=None)`, атрибут `result: UserConfig | None`.
  - `gui/user_list_view.py`: `UserListView(parent, repo)`; методы `refresh()`, `users_for_action(only_enabled: bool) -> list[UserConfig]`.

- [ ] **Step 1: Проверить tkinter и при необходимости установить tk**

Run: `.venv/bin/python -c "import tkinter; print('tkinter OK')"`
Expected: `tkinter OK`.

Если ошибка `libtk8.6.so: cannot open shared object file`, попросить пользователя выполнить:

```bash
sudo pacman -S tk
```

и повторить проверку. Без `tk` GUI не запустится, но юнит-тесты Task 6 не требуют tkinter.

- [ ] **Step 2: Написать падающие тесты валидации**

`tests/test_gui_validation.py`:

```python
from configs.user_config import MANUAL, YOUTRACK, UserConfig
from gui.validation import parse_exclude_date, validate_user_form


def valid_form(**overrides) -> dict[str, str]:
    form = {
        "name": "Олег",
        "driver": YOUTRACK,
        "redmine_api_key": "key",
        "user_id": "16",
        "activity_id": "9",
        "issue_id": "2682",
        "comment": "development",
        "youtrack_access_token": "token",
    }
    form.update(overrides)
    return form


class TestValidateUserForm:
    def test_valid_form_returns_user(self):
        user, errors = validate_user_form(
            valid_form(),
            is_enable=True,
            exclude_dates=["2026-10-01"],
            db_id=5,
        )

        assert errors == []
        assert isinstance(user, UserConfig)
        assert user.name == "Олег"
        assert user.user_id == 16
        assert user.activity_id == 9
        assert user.issue_id == 2682
        assert user.driver == YOUTRACK
        assert user.exclude_dates == ["2026-10-01"]
        assert user.db_id == 5

    def test_empty_name_is_rejected(self):
        user, errors = validate_user_form(valid_form(name="  "), is_enable=True, exclude_dates=[])

        assert user is None
        assert "Имя обязательно" in errors

    def test_non_integer_user_id_is_rejected(self):
        user, errors = validate_user_form(valid_form(user_id="abc"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("user_id" in error for error in errors)

    def test_zero_issue_id_is_rejected(self):
        user, errors = validate_user_form(valid_form(issue_id="0"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("issue_id" in error for error in errors)

    def test_youtrack_requires_token(self):
        user, errors = validate_user_form(
            valid_form(youtrack_access_token=""),
            is_enable=True,
            exclude_dates=[],
        )

        assert user is None
        assert any("token" in error.lower() for error in errors)

    def test_manual_does_not_require_token(self):
        user, errors = validate_user_form(
            valid_form(driver=MANUAL, youtrack_access_token=""),
            is_enable=True,
            exclude_dates=[],
        )

        assert errors == []
        assert user.driver == MANUAL

    def test_invalid_driver_is_rejected(self):
        user, errors = validate_user_form(valid_form(driver="jira"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("driver" in error for error in errors)


class TestParseExcludeDate:
    def test_valid_date_is_normalized(self):
        parsed, error = parse_exclude_date("2026-10-01", [])

        assert parsed == "2026-10-01"
        assert error is None

    def test_invalid_date_returns_error(self):
        parsed, error = parse_exclude_date("01.10.2026", [])

        assert parsed is None
        assert error is not None

    def test_duplicate_returns_error(self):
        parsed, error = parse_exclude_date("2026-10-01", ["2026-10-01"])

        assert parsed is None
        assert error is not None
```

- [ ] **Step 3: Запустить — должно упасть**

Run: `.venv/bin/python -m pytest tests/test_gui_validation.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'gui.validation'`.

- [ ] **Step 4: Создать gui/validation.py**

`gui/validation.py`:

```python
from datetime import date

from configs.user_config import MANUAL, YOUTRACK, UserConfig


def parse_positive_int(value: str, label: str, errors: list[str]) -> int:
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        errors.append(f"{label}: должно быть целым числом")
        return 0
    if parsed <= 0:
        errors.append(f"{label}: должно быть больше нуля")
    return parsed


def validate_user_form(
    form: dict[str, str],
    is_enable: bool,
    exclude_dates: list[str],
    db_id: int | None = None,
) -> tuple[UserConfig | None, list[str]]:
    errors: list[str] = []

    name = form.get("name", "").strip()
    if not name:
        errors.append("Имя обязательно")

    driver = form.get("driver", MANUAL)
    if driver not in (MANUAL, YOUTRACK):
        errors.append("Некорректный driver")

    token = form.get("youtrack_access_token", "").strip()
    if driver == YOUTRACK and not token:
        errors.append("Для youtrack нужен access_token")

    user_id = parse_positive_int(form.get("user_id", ""), "user_id", errors)
    activity_id = parse_positive_int(form.get("activity_id", ""), "activity_id", errors)
    issue_id = parse_positive_int(form.get("issue_id", ""), "issue_id", errors)

    if errors:
        return None, errors

    return (
        UserConfig(
            is_enable=is_enable,
            name=name,
            redmine_api_key=form.get("redmine_api_key", "").strip(),
            user_id=user_id,
            activity_id=activity_id,
            comment=form.get("comment", "").strip(),
            issue_id=issue_id,
            driver=driver,
            youtrack_access_token=token,
            exclude_dates=sorted(exclude_dates),
            db_id=db_id,
        ),
        [],
    )


def parse_exclude_date(value: str, existing: list[str]) -> tuple[str | None, str | None]:
    try:
        parsed = date.fromisoformat(value.strip())
    except ValueError:
        return None, "Дата должна быть в формате ГГГГ-ММ-ДД"

    iso = parsed.isoformat()
    if iso in existing:
        return None, "Дата уже добавлена"

    return iso, None
```

- [ ] **Step 5: Запустить тесты — должны пройти**

Run: `.venv/bin/python -m pytest tests/test_gui_validation.py -q`
Expected: 10 passed.

- [ ] **Step 6: Создать gui/user_editor.py**

`gui/user_editor.py`:

```python
import tkinter as tk
from tkinter import ttk

from configs.user_config import MANUAL, YOUTRACK, UserConfig
from gui.validation import parse_exclude_date, validate_user_form


class UserEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, user: UserConfig | None = None):
        super().__init__(parent)
        self.user = user
        self.result: UserConfig | None = None
        self.exclude_dates = list(user.exclude_dates) if user else []
        self.driver_var = tk.StringVar(value=user.driver if user else MANUAL)
        self.enable_var = tk.BooleanVar(value=user.is_enable if user else True)
        self.show_secrets = tk.BooleanVar(value=False)
        self.fields: dict[str, ttk.Entry] = {}
        self.secret_entries: list[ttk.Entry] = []

        self.title("Изменить юзера" if user else "Добавить юзера")
        self.resizable(False, False)
        self._build_form()
        self._sync_driver()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _add_entry(
        self,
        form: ttk.Frame,
        row: int,
        key: str,
        label: str,
        secret: bool = False,
    ) -> ttk.Entry:
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(form, width=44, show="*" if secret else "")
        entry.grid(row=row, column=1, sticky="we", pady=2)
        if self.user is not None:
            entry.insert(0, str(getattr(self.user, key)))
        if secret:
            self.secret_entries.append(entry)
        self.fields[key] = entry
        return entry

    def _build_form(self) -> None:
        form = ttk.Frame(self, padding=10)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        self._add_entry(form, 0, "name", "Имя")

        ttk.Label(form, text="Driver").grid(row=1, column=0, sticky="w", pady=2)
        driver_frame = ttk.Frame(form)
        driver_frame.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(
            driver_frame,
            text="manual",
            variable=self.driver_var,
            value=MANUAL,
            command=self._sync_driver,
        ).pack(side="left")
        ttk.Radiobutton(
            driver_frame,
            text="youtrack",
            variable=self.driver_var,
            value=YOUTRACK,
            command=self._sync_driver,
        ).pack(side="left")

        self._add_entry(form, 2, "redmine_api_key", "redmine_api_key", secret=True)
        self._add_entry(form, 3, "user_id", "user_id")
        self._add_entry(form, 4, "activity_id", "activity_id")
        self._add_entry(form, 5, "issue_id", "issue_id")
        self._add_entry(form, 6, "comment", "Комментарий")
        self.token_entry = self._add_entry(
            form, 7, "youtrack_access_token", "youtrack_access_token", secret=True
        )

        ttk.Checkbutton(
            form,
            text="показать ключи",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).grid(row=8, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(form, text="включён", variable=self.enable_var).grid(
            row=9, column=1, sticky="w"
        )

        dates_frame = ttk.LabelFrame(form, text="Исключённые даты", padding=6)
        dates_frame.grid(row=10, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.dates_list = tk.Listbox(dates_frame, height=4, width=16)
        self.dates_list.grid(row=0, column=0, rowspan=3, sticky="we")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry = ttk.Entry(dates_frame, width=14)
        self.date_entry.grid(row=0, column=1, padx=6)
        ttk.Button(dates_frame, text="Добавить", command=self._add_date).grid(
            row=1, column=1, padx=6, sticky="we"
        )
        ttk.Button(dates_frame, text="Удалить", command=self._remove_date).grid(
            row=2, column=1, padx=6, sticky="we"
        )

        self.error_label = ttk.Label(form, text="", foreground="red", wraplength=420)
        self.error_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(form)
        buttons.grid(row=12, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Сохранить", command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="left")

    def _sync_driver(self) -> None:
        state = "normal" if self.driver_var.get() == YOUTRACK else "disabled"
        self.token_entry.configure(state=state)

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
        self.dates_list.insert("end", parsed)
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
        form["driver"] = self.driver_var.get()
        user, errors = validate_user_form(
            form,
            is_enable=self.enable_var.get(),
            exclude_dates=self.exclude_dates,
            db_id=self.user.db_id if self.user else None,
        )
        if errors:
            self.error_label.configure(text="\n".join(errors))
            return
        self.result = user
        self.destroy()
```

- [ ] **Step 7: Создать gui/user_list_view.py**

`gui/user_list_view.py`:

```python
from tkinter import messagebox, ttk

from configs.user_config import UserConfig
from gui.user_editor import UserEditor
from storage.user_repository import UserRepository


class UserListView(ttk.LabelFrame):
    def __init__(self, parent, repo: UserRepository):
        super().__init__(parent, text="Юзеры", padding=4)
        self.repo = repo
        self.users_by_iid: dict[str, UserConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        buttons = (
            ("Добавить", self.add_user),
            ("Изменить", self.edit_user),
            ("Удалить", self.delete_user),
            ("Вкл/Выкл", self.toggle_user),
        )
        for text, command in buttons:
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=2)

        columns = ("enable", "name", "driver", "issue", "user_id", "activity_id", "comment")
        headings = {
            "enable": ("Вкл", 50),
            "name": ("Имя", 140),
            "driver": ("Driver", 90),
            "issue": ("Issue", 80),
            "user_id": ("user_id", 80),
            "activity_id": ("activity_id", 90),
            "comment": ("Комментарий", 180),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda event: self.edit_user())
        self.tree.bind("<space>", lambda event: self.toggle_user())

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.users_by_iid.clear()
        for user in self.repo.list_users():
            iid = self.tree.insert(
                "",
                "end",
                values=(
                    "☑" if user.is_enable else "☐",
                    user.name,
                    user.driver,
                    user.issue_id,
                    user.user_id,
                    user.activity_id,
                    user.comment,
                ),
            )
            self.users_by_iid[iid] = user

    def selected_user(self) -> UserConfig | None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Fill Redmine", "Выберите юзера", parent=self)
            return None
        return self.users_by_iid[selection[0]]

    def users_for_action(self, only_enabled: bool) -> list[UserConfig]:
        users = self.repo.list_users()
        if only_enabled:
            return [user for user in users if user.is_enable]
        selected = [self.users_by_iid[iid] for iid in self.tree.selection()]
        return selected or users

    def add_user(self) -> None:
        editor = UserEditor(self, None)
        self.wait_window(editor)
        if editor.result:
            self.repo.add_user(editor.result)
            self.refresh()

    def edit_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        editor = UserEditor(self, user)
        self.wait_window(editor)
        if editor.result:
            self.repo.update_user(user.db_id, editor.result)
            self.refresh()

    def delete_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        if messagebox.askyesno("Fill Redmine", f"Удалить юзера «{user.name}»?", parent=self):
            self.repo.delete_user(user.db_id)
            self.refresh()

    def toggle_user(self) -> None:
        user = self.selected_user()
        if user is None:
            return
        self.repo.set_enabled(user.db_id, not user.is_enable)
        self.refresh()
```

- [ ] **Step 8: Проверить компиляцию и тесты**

Run: `.venv/bin/python -m compileall gui storage -q`
Expected: без ошибок.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

- [ ] **Step 9: Коммит**

```bash
git add gui/validation.py gui/user_editor.py gui/user_list_view.py tests/test_gui_validation.py
git commit -m "Add user list view and editor dialog"
```

---

### Task 7: GUI — worker, форматирование, панель импорта

**Files:**
- Create: `gui/worker.py`
- Create: `gui/formatting.py`
- Create: `gui/import_view.py`
- Test: `tests/test_gui_worker.py`
- Test: `tests/test_gui_formatting.py`

**Interfaces:**
- Consumes: `ImportService`, `PreparedImport`, `ImportSummary` (Task 4), `PreviewDTO`, `DateRangeDTO` (Task 3).
- Produces:
  - `GuiWorker(root)`: `register(kind, handler)`, `send(kind, payload=None)`, `submit(func, done_kind="done", error_kind="error")`, `drain()`.
  - `gui/formatting.py`: `format_hours(hours) -> str`, `format_range(rng: DateRangeDTO) -> str`, `format_ranges(ranges) -> str`.
  - `gui/import_view.py`: `ImportView(parent, service, worker, get_users)`, атрибуты `prepared`, `busy`; методы `build_preview()`, `run_import()`.

- [ ] **Step 1: Написать падающие тесты worker**

`tests/test_gui_worker.py`:

```python
import time

from gui.worker import GuiWorker


class FakeRoot:
    def after(self, delay, callback):
        return None


def wait_until(worker, predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        worker.drain()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestGuiWorker:
    def test_drain_dispatches_registered_handlers(self):
        worker = GuiWorker(FakeRoot())
        received = []
        worker.register("log", received.append)

        worker.send("log", "привет")
        worker.send("unknown", "ignored")
        worker.drain()

        assert received == ["привет"]

    def test_submit_reports_function_result(self):
        worker = GuiWorker(FakeRoot())
        done = []
        worker.register("done", done.append)

        worker.submit(lambda: 42)

        assert wait_until(worker, lambda: done == [42])

    def test_submit_reports_exception(self):
        worker = GuiWorker(FakeRoot())
        errors = []
        worker.register("error", errors.append)

        def boom():
            raise ValueError("bad")

        worker.submit(boom)

        assert wait_until(worker, lambda: len(errors) == 1)
        assert isinstance(errors[0], ValueError)
```

- [ ] **Step 2: Запустить — должно упасть**

Run: `.venv/bin/python -m pytest tests/test_gui_worker.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'gui.worker'`.

- [ ] **Step 3: Создать gui/worker.py**

`gui/worker.py` (без импорта tkinter — потокобезопасная логика):

```python
import queue
import threading
from collections.abc import Callable
from typing import Any


class GuiWorker:
    def __init__(self, root: Any):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.handlers: dict[str, Callable[[Any], None]] = {}
        self.root.after(100, self._poll)

    def register(self, kind: str, handler: Callable[[Any], None]) -> None:
        self.handlers[kind] = handler

    def send(self, kind: str, payload: Any = None) -> None:
        self.queue.put((kind, payload))

    def submit(
        self,
        func: Callable[[], Any],
        done_kind: str = "done",
        error_kind: str = "error",
    ) -> None:
        def target() -> None:
            try:
                result = func()
            except Exception as exc:
                self.send(error_kind, exc)
            else:
                self.send(done_kind, result)

        threading.Thread(target=target, daemon=True).start()

    def drain(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                return
            handler = self.handlers.get(kind)
            if handler is not None:
                handler(payload)

    def _poll(self) -> None:
        self.drain()
        self.root.after(100, self._poll)
```

- [ ] **Step 4: Запустить тесты worker — должны пройти**

Run: `.venv/bin/python -m pytest tests/test_gui_worker.py -q`
Expected: 3 passed.

- [ ] **Step 5: Написать падающие тесты форматирования**

`tests/test_gui_formatting.py`:

```python
from dto.preview_dto import DateRangeDTO
from gui.formatting import format_hours, format_range, format_ranges


class TestFormatHours:
    def test_integer_hours(self):
        assert format_hours(8) == "8"

    def test_fractional_hours(self):
        assert format_hours(7.5) == "7.5"


class TestFormatRange:
    def test_single_day(self):
        rng = DateRangeDTO(start_date="2026-10-01", end_date="2026-10-01", hours=8)

        assert format_range(rng) == "01.10 — 8h"

    def test_period(self):
        rng = DateRangeDTO(start_date="2026-10-01", end_date="2026-10-04", hours=8)

        assert format_range(rng) == "01.10–04.10 — 8h"


class TestFormatRanges:
    def test_empty_list(self):
        assert format_ranges([]) == ""

    def test_multiple_ranges_joined(self):
        ranges = [
            DateRangeDTO(start_date="2026-10-01", end_date="2026-10-02", hours=8),
            DateRangeDTO(start_date="2026-10-05", end_date="2026-10-05", hours=4),
        ]

        assert format_ranges(ranges) == "01.10–02.10 — 8h; 05.10 — 4h"
```

- [ ] **Step 6: Запустить — должно упасть**

Run: `.venv/bin/python -m pytest tests/test_gui_formatting.py -q`
Expected: FAIL с `ModuleNotFoundError: No module named 'gui.formatting'`.

- [ ] **Step 7: Создать gui/formatting.py**

`gui/formatting.py`:

```python
from datetime import date

from dto.preview_dto import DateRangeDTO


def format_hours(hours: int | float) -> str:
    return f"{hours:g}"


def format_range(rng: DateRangeDTO) -> str:
    start = date.fromisoformat(rng.start_date).strftime("%d.%m")
    end = date.fromisoformat(rng.end_date).strftime("%d.%m")
    if rng.start_date == rng.end_date:
        return f"{start} — {format_hours(rng.hours)}h"
    return f"{start}–{end} — {format_hours(rng.hours)}h"


def format_ranges(ranges: list[DateRangeDTO]) -> str:
    return "; ".join(format_range(rng) for rng in ranges)
```

- [ ] **Step 8: Запустить тесты форматирования**

Run: `.venv/bin/python -m pytest tests/test_gui_formatting.py -q`
Expected: 6 passed.

- [ ] **Step 9: Создать gui/import_view.py**

`gui/import_view.py`:

```python
import asyncio
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from gui.formatting import format_hours, format_range
from gui.worker import GuiWorker
from services.import_service import ImportService, ImportSummary, PreparedImport


class ImportView(ttk.LabelFrame):
    def __init__(
        self,
        parent,
        service: ImportService,
        worker: GuiWorker,
        get_users: Callable[[bool], list],
    ):
        super().__init__(parent, text="Превью и импорт", padding=4)
        self.service = service
        self.worker = worker
        self.get_users = get_users
        self.prepared: list[PreparedImport] = []
        self.busy = False
        self._build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.worker.register("log", self.log)
        self.worker.register("preview_done", self._on_preview_done)
        self.worker.register("import_done", self._on_import_done)
        self.worker.register("error", self._on_worker_error)
        self.worker.register("progress", self._on_progress)

    def _build(self) -> None:
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.preview_button = ttk.Button(
            buttons, text="Построить превью", command=self.build_preview
        )
        self.preview_button.pack(side="left", padx=2)
        self.import_button = ttk.Button(
            buttons, text="Запустить импорт", command=self.run_import, state="disabled"
        )
        self.import_button.pack(side="left", padx=2)
        self.only_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            buttons,
            text="только включённые",
            variable=self.only_enabled,
        ).pack(side="left", padx=8)

        columns = ("user", "driver", "issue", "subject", "periods", "total")
        headings = {
            "user": ("Имя", 130),
            "driver": ("Driver", 80),
            "issue": ("Issue", 70),
            "subject": ("Тема", 220),
            "periods": ("Периоды", 260),
            "total": ("Всего", 70),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
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
        self.log_text = tk.Text(log_frame, height=9, state="disabled", wrap="word")
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
        state = "disabled" if busy else "normal"
        self.preview_button.configure(state=state)
        can_import = not busy and bool(self.prepared)
        self.import_button.configure(state="normal" if can_import else "disabled")

    def build_preview(self) -> None:
        users = self.get_users(self.only_enabled.get())
        if not users:
            messagebox.showinfo("Fill Redmine", "Нет юзеров для превью", parent=self)
            return
        self.prepared = []
        self.import_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.log("Строю превью...")
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.prepare(users),
            done_kind="preview_done",
            error_kind="error",
        )

    def _on_preview_done(self, items: list[PreparedImport]) -> None:
        self.prepared = items
        for item in items:
            preview = item.preview
            parent = self.tree.insert(
                "",
                "end",
                values=(
                    preview.user_name,
                    preview.driver,
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
                    values=("", "", "", "", format_range(date_range), format_hours(date_range.hours)),
                )
        self._set_busy(False)
        self.log(f"Превью готово: юзеров {len(items)}")
        if not items:
            messagebox.showinfo("Fill Redmine", "Нет записей для импорта", parent=self)

    def run_import(self) -> None:
        if not self.prepared:
            messagebox.showinfo("Fill Redmine", "Сначала постройте превью", parent=self)
            return
        total = sum(len(item.records) for item in self.prepared)
        question = f"Импортировать {total} записей для {len(self.prepared)} юзеров?"
        if not messagebox.askyesno("Fill Redmine", question, parent=self):
            return
        items = self.prepared
        self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.progress_label.set("")
        self._set_busy(True)

        def progress_cb(completed: int, global_total: int, name: str) -> None:
            self.worker.send("progress", (completed, global_total, name))

        self.worker.submit(
            lambda: asyncio.run(self.service.run(items, progress_cb=progress_cb)),
            done_kind="import_done",
            error_kind="error",
        )

    def _on_progress(self, payload: tuple[int, int, str]) -> None:
        completed, total, name = payload
        self.progress_bar.configure(value=completed)
        self.progress_label.set(f"{name} {completed}/{total}")

    def _on_import_done(self, summary: ImportSummary) -> None:
        self.prepared = []
        self._set_busy(False)
        self.progress_label.set("")
        message = f"Импорт завершён: {summary.total} записей, ошибок: {len(summary.errors)}"
        self.log(message)
        for user_name, spent_on, error in summary.errors:
            self.log(f"  {user_name} {spent_on}: {error}")
        messagebox.showinfo("Fill Redmine", message, parent=self)

    def _on_worker_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Fill Redmine", str(exc), parent=self)
```

- [ ] **Step 10: Проверить компиляцию, тесты и коммит**

Run: `.venv/bin/python -m compileall gui -q`
Expected: без ошибок.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

```bash
git add gui/worker.py gui/formatting.py gui/import_view.py tests/test_gui_worker.py tests/test_gui_formatting.py
git commit -m "Add background worker and import panel"
```

---

### Task 8: GUI — главное окно и точка входа

**Files:**
- Create: `gui/app.py`
- Create: `fill_redmine_gui.py`

**Interfaces:**
- Consumes: `UserListView` (Task 6), `ImportView`, `GuiWorker` (Task 7), `ImportService` (Task 4), `UserRepository` (Task 1), `migrate_from_user_list` (Task 2).
- Produces: `MainWindow(repo)` (наследник `tk.Tk`); `fill_redmine_gui.main()`.

- [ ] **Step 1: Создать gui/app.py**

`gui/app.py`:

```python
import tkinter as tk
from tkinter import messagebox, ttk

from gui.import_view import ImportView
from gui.user_list_view import UserListView
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.user_repository import UserRepository


class MainWindow(tk.Tk):
    def __init__(self, repo: UserRepository):
        super().__init__()
        self.repo = repo
        self.worker = GuiWorker(self)
        self.service = ImportService(log=lambda message: self.worker.send("log", message))

        self.title("Fill Redmine")
        self.geometry("1000x760")
        self.minsize(900, 600)

        self.user_list_view = UserListView(self, repo)
        self.user_list_view.pack(fill="both", expand=False, padx=6, pady=6)

        self.import_view = ImportView(
            self,
            service=self.service,
            worker=self.worker,
            get_users=self.user_list_view.users_for_action,
        )
        self.import_view.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self,
            textvariable=self.status,
            relief="sunken",
            anchor="w",
            padding=2,
        ).pack(fill="x", side="bottom")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self.import_view.busy:
            question = "Импорт выполняется. Закрыть окно?"
            if not messagebox.askyesno("Fill Redmine", question, parent=self):
                return
        self.destroy()
```

- [ ] **Step 2: Создать fill_redmine_gui.py**

`fill_redmine_gui.py`:

```python
from gui.app import MainWindow
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository


def main() -> None:
    repository = UserRepository()
    migrate_from_user_list(repository, log=print)
    app = MainWindow(repository)
    app.mainloop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Проверить компиляцию и тесты**

Run: `.venv/bin/python -m compileall gui fill_redmine_gui.py -q`
Expected: без ошибок.

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

- [ ] **Step 4: Ручная проверка GUI (выполняет пользователь)**

Важно: первый запуск переносит реальный `user_list.py` в БД и переименовывает его в
`user_list.py.migrated` — это ожидаемое поведение с бэкапом. Если переносить не нужно —
предварительно скопируйте файл вручную.

Run: `.venv/bin/python fill_redmine_gui.py`
Expected:
1. Окно «Fill Redmine» со списком юзеров; если был `user_list.py` — в списке появился юзер, рядом лежит `user_list.py.migrated`.
2. «Добавить» → заполнить поля → ошибки валидации при пустом имени/нулевых id; успешное сохранение добавляет строку.
3. «Изменить»/«Удалить»/«Вкл/Выкл» работают; после перезапуска изменения сохраняются.
4. `stat -c %a fill_redmine.db` → `600`.
5. «Построить превью» (нужны реальные сеть и ключи) → таблица с периодами; «Запустить импорт» → подтверждение, прогресс-бар и лог.

Если GUI запускался с реальным импортом — это создаст записи в Redmine; для проверки без
побочных эффектов использовать превью и отменять импорт.

- [ ] **Step 5: Коммит**

```bash
git add gui/app.py fill_redmine_gui.py
git commit -m "Add main GUI window and entry point"
```

---

### Task 9: Ярлык в меню и автопин на панель

**Files:**
- Create: `assets/fill_redmine.svg`
- Create: `run_gui.sh`
- Create: `scripts/install_desktop.sh`

**Interfaces:**
- Consumes: `fill_redmine_gui.py` (Task 8).
- Produces: `~/.local/share/applications/fill-redmine-gui.desktop`; автопин в Plasma 6 через `qdbus6`.

- [ ] **Step 1: Создать иконку**

`assets/fill_redmine.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <rect x="8" y="8" width="112" height="112" rx="24" fill="#c0392b"/>
  <circle cx="64" cy="64" r="40" fill="none" stroke="#ffffff" stroke-width="8"/>
  <line x1="64" y1="64" x2="64" y2="40" stroke="#ffffff" stroke-width="8" stroke-linecap="round"/>
  <line x1="64" y1="64" x2="82" y2="74" stroke="#ffffff" stroke-width="8" stroke-linecap="round"/>
</svg>
```

- [ ] **Step 2: Создать run_gui.sh**

`run_gui.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif [[ -x "$SCRIPT_DIR/venv/bin/python" ]]; then
    PYTHON="$SCRIPT_DIR/venv/bin/python"
else
    PYTHON="python3"
fi
exec "$PYTHON" "$SCRIPT_DIR/fill_redmine_gui.py"
```

```bash
chmod +x run_gui.sh
```

- [ ] **Step 3: Создать scripts/install_desktop.sh**

`scripts/install_desktop.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_ID="fill-redmine-gui"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/$APP_ID.desktop"

if ! python3 -c "import tkinter" >/dev/null 2>&1; then
    echo "tkinter не найден. Установите: sudo pacman -S tk"
    exit 1
fi

chmod +x "$PROJECT_DIR/run_gui.sh"
mkdir -p "$DESKTOP_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Fill Redmine
Comment=Импорт временных записей из YouTrack в Redmine
Exec=$PROJECT_DIR/run_gui.sh
Path=$PROJECT_DIR
Icon=$PROJECT_DIR/assets/fill_redmine.svg
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
            var entry = "applications:fill-redmine-gui.desktop";
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

```bash
chmod +x scripts/install_desktop.sh
```

- [ ] **Step 4: Ручная проверка ярлыка (выполняет пользователь)**

Run: `bash scripts/install_desktop.sh`
Expected:
1. Сообщение «Ярлык установлен и закреплён на панели.» или инструкция для ручного закрепа.
2. `~/.local/share/applications/fill-redmine-gui.desktop` существует.
3. В меню приложений есть «Fill Redmine» с иконкой-часами.
4. Клик по ярлыку открывает GUI; иконка появляется на панели.

- [ ] **Step 5: Коммит**

```bash
git add assets/fill_redmine.svg run_gui.sh scripts/install_desktop.sh
git commit -m "Add desktop shortcut installer with Plasma autopin"
```

---

### Task 10: README и финальная проверка

**Files:**
- Modify: `README.md`
- Verify: `requirements-dev.txt`

**Interfaces:**
- Consumes: всё предыдущее.
- Produces: актуальная документация.

- [ ] **Step 1: Обновить README.md**

Новое содержимое `README.md`:

````markdown
# Fill Redmine

Импорт временных записей из YouTrack в Redmine. Юзеры хранятся в SQLite, управление — через GUI или CLI.

## Установка

### 1. Системные зависимости

```bash
sudo pacman -S tk
```

`tk` нужен для Tkinter-GUI.

### 2. Виртуальное окружение

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Настройка окружения

```bash
cp .env.example .env
```

Заполните `REDMINE_BASE_URL` и `YOUTRACK_BASE_URL`.

## GUI

```bash
python fill_redmine_gui.py
```

Первое окно содержит список юзеров (добавление, редактирование, удаление, вкл/выкл),
панель превью и импорта с прогрессом и логом. Включённые юзеры хранятся в
`fill_redmine.db` (права 600, путь переопределяется переменной `FILL_REDMINE_DB`).

При первом запуске, если база пуста и существует `user_list.py`, юзеры переносятся в БД,
а файл переименовывается в `user_list.py.migrated`.

### Ярлык на панели KDE

```bash
bash scripts/install_desktop.sh
```

Скрипт ставит ярлык в меню приложений и пытается закрепить его на панели Plasma 6.
Если автопин не удался — закрепите вручную: ПКМ по иконке → «Закрепить на панели».

## CLI

```bash
python fill_redmine.py
python fill_redmine.py --id 1234
```

CLI читает юзеров из той же SQLite-базы.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

## Структура проекта

- `fill_redmine.py` — CLI
- `fill_redmine_gui.py` — точка входа GUI
- `gui/` — окна и виджеты Tkinter
- `storage/` — SQLite: схема, репозиторий, миграция
- `services/` — превью и импорт
- `imports/` — импортеры (manual/youtrack)
- `clients/` — API-клиенты Redmine и YouTrack
- `dto/` — объекты передачи данных
- `configs/` — конфигурация и `UserConfig`
- `scripts/install_desktop.sh` — установка ярлыка
````

- [ ] **Step 2: Финальная проверка**

Run: `.venv/bin/python -m pytest -q`
Expected: все тесты PASS.

Run: `.venv/bin/python -m compileall fill_redmine.py fill_redmine_gui.py gui storage services imports clients dto configs -q`
Expected: без ошибок.

Run: `.venv/bin/python fill_redmine.py --help`
Expected: справка с `--id`.

Run: `git status --short`
Expected: не должно быть `fill_redmine.db` и `user_list.py.migrated` (они в `.gitignore`).

- [ ] **Step 3: Коммит**

```bash
git add README.md
git commit -m "Document GUI, SQLite storage and desktop shortcut"
```
