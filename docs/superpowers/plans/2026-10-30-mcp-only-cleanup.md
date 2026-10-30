# MCP-only Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every GUI, CLI, storage, service and AI artifact from the repository, leaving only the MCP server and the code it needs.

**Architecture:** Delete non-MCP runtime/test/doc trees in dependency order, then trim GUI helpers from the remaining tracker core, and rewrite the operator documentation for MCP-only operation. Local user data and git history stay untouched.

**Tech Stack:** Python 3.10+, MCP Python SDK v2, pytest, git.

## Global Constraints

- MCP stdio (`python -m mcp_server`) is the only supported entry point.
- Do not delete or modify `.env`, `config/users.json`, `work_assistant.db`, `user_list.py.migrated`, or `.git` history.
- Do not change MCP tool names, arguments, return shapes, or write rules.
- Use absolute imports and type hints in remaining code.
- Max line length: 100 characters.
- Tests must use in-memory MCP clients and fakes; no live tracker requests.
- Run `.venv/bin/pytest -q` before every commit; each task ends green with its own commit.
- If a deletion breaks an import, fix the remaining code rather than restoring the deleted module.

---

### Task 1: Remove GUI/CLI Runtime and GUI Tests

**Files:**
- Delete: `gui/`
- Delete: `work_assistant.py`
- Delete: `fill_redmine_gui.py`
- Delete: `run_gui.sh`
- Delete: `Work Assistant.desktop`
- Delete: `scripts/install_desktop.sh`
- Delete: `assets/work_assistant.svg`
- Delete: `DTD XHTML`
- Delete tests: `tests/test_gui_formatting.py`, `tests/test_gui_validation.py`, `tests/test_gui_worker.py`, `tests/test_report_editor_validation.py`, `tests/test_settings_validation.py`, `tests/test_tracking_validation.py`, `tests/test_ai_settings_validation.py`

**Interfaces:**
- Consumes: existing green baseline.
- Produces: no GUI/CLI runtime; backend modules still present for Task 2.

- [ ] **Step 1: Run the baseline suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all 326 tests pass. If not, stop and report the failure.

- [ ] **Step 2: Remove GUI/CLI runtime files**

Run:

```bash
git rm -r gui
git rm work_assistant.py fill_redmine_gui.py run_gui.sh "Work Assistant.desktop"
git rm scripts/install_desktop.sh assets/work_assistant.svg "DTD XHTML"
rm -rf gui/__pycache__
rmdir scripts assets 2>/dev/null || true
```

- [ ] **Step 3: Remove GUI-only tests**

Run:

```bash
git rm tests/test_gui_formatting.py tests/test_gui_validation.py tests/test_gui_worker.py
git rm tests/test_report_editor_validation.py tests/test_settings_validation.py
git rm tests/test_tracking_validation.py tests/test_ai_settings_validation.py
```

- [ ] **Step 4: Verify the runtime is gone**

Run:

```bash
test ! -e gui
test ! -e work_assistant.py
test ! -e fill_redmine_gui.py
test ! -e run_gui.sh
test ! -e "Work Assistant.desktop"
test ! -e scripts/install_desktop.sh
test ! -e assets/work_assistant.svg
test ! -e "DTD XHTML"
```

Expected: every command exits 0.

- [ ] **Step 5: Run the remaining suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all remaining tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add -A
git commit -m "refactor: remove GUI and CLI entry points"
```

---

### Task 2: Remove Non-MCP Backend and Its Tests

**Files:**
- Delete: `services/`
- Delete: `storage/`
- Delete: `clients/ai/`
- Delete: `configs/ai_settings.py`
- Delete: `configs/iterable_config_dto.py`
- Delete: `configs/user_config.py`
- Delete: `dto/commit_plan_dto.py`
- Delete: `dto/tracking_dto.py`
- Keep for now: `configs/project_config.py` (still imported by `trackers/registry.py`; Task 3 removes it)
- Delete tests: `tests/test_ai_providers.py`, `tests/test_database.py`, `tests/test_migration.py`, `tests/test_migration_v2.py`, `tests/test_project_migration.py`, `tests/test_project_repository.py`, `tests/test_settings_repository.py`, `tests/test_tracking_service.py`, `tests/test_tracking_write.py`, `tests/test_user_config.py`, `tests/test_user_repository.py`

**Interfaces:**
- Consumes: Task 1 removed GUI/CLI.
- Produces: only MCP core and tracker/client/DTO/config modules remain; `configs/project_config.py` is the one temporary leftover.

- [ ] **Step 1: Remove non-MCP backend code**

Run:

```bash
git rm -r services storage clients/ai
git rm configs/ai_settings.py configs/iterable_config_dto.py configs/user_config.py
git rm dto/commit_plan_dto.py dto/tracking_dto.py
rm -rf services storage clients/ai
rm -rf configs/__pycache__ dto/__pycache__ clients/__pycache__
```

- [ ] **Step 2: Remove backend-only tests**

Run:

```bash
git rm tests/test_ai_providers.py tests/test_database.py
git rm tests/test_migration.py tests/test_migration_v2.py tests/test_project_migration.py
git rm tests/test_project_repository.py tests/test_settings_repository.py
git rm tests/test_tracking_service.py tests/test_tracking_write.py
git rm tests/test_user_config.py tests/test_user_repository.py
```

- [ ] **Step 3: Verify removed packages are gone**

Run:

```bash
test ! -e services
test ! -e storage
test ! -e clients/ai
test ! -e configs/ai_settings.py
test ! -e configs/user_config.py
test ! -e configs/iterable_config_dto.py
test ! -e dto/commit_plan_dto.py
test ! -e dto/tracking_dto.py
```

Expected: every command exits 0.

- [ ] **Step 4: Run the remaining suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all remaining tests pass. `configs/project_config.py` is still present, so `test_tracker_registry.py` remains valid.

- [ ] **Step 5: Commit**

Run:

```bash
git add -A
git commit -m "refactor: remove non-MCP backend"
```

---

### Task 3: Trim GUI Helpers from the MCP Core

**Files:**
- Modify: `trackers/base.py`
- Modify: `trackers/registry.py`
- Modify: `trackers/__init__.py`
- Modify: `trackers/redmine.py`
- Modify: `trackers/youtrack.py`
- Modify: `clients/git_client.py`
- Modify: `tests/test_tracker_registry.py`
- Modify: `tests/test_redmine_tracker.py`
- Modify: `tests/test_youtrack_tracker.py`
- Modify: `tests/test_git_client.py`
- Delete: `configs/project_config.py`

**Interfaces:**
- Consumes: Task 2 left only MCP core plus `configs/project_config.py`.
- Produces: `BaseTracker` without form-field helpers; registry without GUI builders; no `ProjectConfig`.

- [ ] **Step 1: Replace `trackers/base.py`**

Write exactly:

```python
from abc import ABC, abstractmethod
from datetime import date

from dto.worklog_dto import WorklogDTO


class BaseTracker(ABC):
    kind: str = ""
    label: str = ""
    can_write: bool = False

    def __init__(self, config: dict) -> None:
        self.config = config or {}

    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        raise NotImplementedError

    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError(
            f"Трекер {self.label} не поддерживает запись часов"
        )
```

- [ ] **Step 2: Replace `trackers/registry.py`**

Write exactly:

```python
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


def get_tracker_class(kind: str) -> type[BaseTracker] | None:
    return _REGISTRY.get(kind)
```

- [ ] **Step 3: Replace `trackers/__init__.py`**

Write exactly:

```python
from trackers.base import BaseTracker
from trackers.registry import get_tracker_class, register_tracker

from trackers.redmine import RedmineTracker  # noqa: E402,F401
from trackers.youtrack import YoutrackTracker  # noqa: E402,F401

__all__ = [
    "BaseTracker",
    "get_tracker_class",
    "register_tracker",
]
```

- [ ] **Step 4: Remove GUI form fields from the concrete trackers**

In `trackers/redmine.py`, change the import line to:

```python
from trackers.base import BaseTracker
```

and delete the `fields = (...)` block. Keep `kind`, `label`, `can_write`, `get_time_entries`, `get_worklogs`, `delete_time_entries`, `create_worklogs`.

In `trackers/youtrack.py`, change the import line to:

```python
from trackers.base import BaseTracker
```

and delete the `fields = (...)` block. Keep `kind`, `label`, `can_write`, `get_worklogs`, `create_worklogs`.

- [ ] **Step 5: Remove the GUI-only git helper**

In `clients/git_client.py`, delete the `get_config_email` method:

```python
    def get_config_email(self) -> str:
        self.validate()
        return self._run("config", "user.email").strip()
```

Keep `validate()`, `_run` and `list_commits`.

- [ ] **Step 6: Rewrite `tests/test_tracker_registry.py`**

Write exactly:

```python
from datetime import date

import pytest

from trackers import registry
from trackers.base import BaseTracker
from trackers.registry import get_tracker_class, register_tracker


@pytest.fixture(autouse=True)
def _isolated_registry():
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


class FakeTracker(BaseTracker):
    kind = "fake_test"
    label = "Fake"

    def get_worklogs(self, start: date, end: date):
        return []


def test_register_and_get():
    register_tracker(FakeTracker)

    assert get_tracker_class("fake_test") is FakeTracker


def test_duplicate_registration_raises():
    register_tracker(FakeTracker)

    with pytest.raises(ValueError):
        register_tracker(FakeTracker)
```

- [ ] **Step 7: Remove the remaining GUI-helper tests**

In `tests/test_redmine_tracker.py`, delete:

```python
def test_tracker_is_configured():
    assert RedmineTracker({"api_key": "key", "user_id": 1, "activity_id": 2, "issue_id": 3}).is_configured()
    assert not RedmineTracker({}).is_configured()
```

In `tests/test_youtrack_tracker.py`, delete:

```python
def test_tracker_is_configured():
    assert YoutrackTracker(
        {"access_token": "token", "issue_id": "PROJ-1"}
    ).is_configured()
    assert not YoutrackTracker({}).is_configured()
```

In `tests/test_git_client.py`, delete:

```python
def test_get_config_email(repo):
    assert GitClient(repo).get_config_email() == "oleg@example.com"
```

- [ ] **Step 8: Delete `configs/project_config.py`**

Run:

```bash
git rm configs/project_config.py
rm -rf configs/__pycache__
```

- [ ] **Step 9: Audit removed symbols**

Run:

```bash
rg -n "TrackerField|configured_trackers|all_trackers|is_configured|validate_config|get_config_email" mcp_server clients trackers tests
rg -n "from trackers(\.registry)? import .*build_tracker|trackers\.build_tracker|registry\.build_tracker" mcp_server clients trackers tests
```

Expected: no matches in both commands (ripgrep exit status 1). The local fake
helper named `build_tracker` inside `tests/test_mcp_write_tools.py` is
unrelated and may remain.

- [ ] **Step 10: Run the suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all remaining tests pass.

- [ ] **Step 11: Commit**

Run:

```bash
git add -A
git commit -m "refactor: remove GUI helpers from MCP core"
```

---

### Task 4: Remove Non-MCP Docs and Fix MCP Design References

**Files:**
- Delete: `docs/superpowers/specs/2026-10-06-gui-sqlite-users-design.md`
- Delete: `docs/superpowers/specs/2026-10-26-work-assistant-projects-design.md`
- Delete: `docs/superpowers/specs/2026-10-27-work-assistant-tracking-redesign.md`
- Delete: `docs/superpowers/specs/2026-10-28-work-assistant-gui-removal-design.md`
- Delete: `docs/superpowers/plans/2026-10-06-gui-sqlite-users.md`
- Delete: `docs/superpowers/plans/2026-10-26-work-assistant-projects.md`
- Delete: `docs/superpowers/plans/2026-10-27-work-assistant-tracking-v2.md`
- Delete: `docs/superpowers/plans/2026-10-28-work-assistant-gui-removal.md`
- Modify: `docs/superpowers/specs/2026-10-28-work-assistant-mcp-design.md`

**Interfaces:**
- Consumes: MCP-only code from Tasks 1–3.
- Produces: docs tree containing only MCP-related specs/plans.

- [ ] **Step 1: Delete non-MCP docs**

Run:

```bash
git rm docs/superpowers/specs/2026-10-06-gui-sqlite-users-design.md
git rm docs/superpowers/specs/2026-10-26-work-assistant-projects-design.md
git rm docs/superpowers/specs/2026-10-27-work-assistant-tracking-redesign.md
git rm docs/superpowers/specs/2026-10-28-work-assistant-gui-removal-design.md
git rm docs/superpowers/plans/2026-10-06-gui-sqlite-users.md
git rm docs/superpowers/plans/2026-10-26-work-assistant-projects.md
git rm docs/superpowers/plans/2026-10-27-work-assistant-tracking-v2.md
git rm docs/superpowers/plans/2026-10-28-work-assistant-gui-removal.md
```

- [ ] **Step 2: Update the MCP design introduction**

In `docs/superpowers/specs/2026-10-28-work-assistant-mcp-design.md`, replace:

```text
Изменение выполняется раньше удаления GUI. GUI-removal описан отдельной
спецификацией и начинается только после проверки MCP-сценариев.
```

with:

```text
GUI, CLI, storage, services и AI-клиенты удалены в MCP-only cleanup
(`2026-10-30-mcp-only-cleanup-design.md`); MCP остаётся единственным
интерфейсом.
```

- [ ] **Step 3: Update the MCP design stages**

Replace:

```text
2. Удалить GUI отдельным изменением по
   `2026-10-28-work-assistant-gui-removal-design.md`.
```

with:

```text
2. Удалить GUI и не-MCP код по
   `2026-10-30-mcp-only-cleanup-design.md`.
```

- [ ] **Step 4: Verify only MCP docs remain**

Run:

```bash
ls docs/superpowers/specs docs/superpowers/plans
```

Expected specs:

```text
2026-10-28-work-assistant-mcp-design.md
2026-10-30-mcp-only-cleanup-design.md
2026-10-30-youtrack-to-redmine-transfer-design.md
```

Expected plans:

```text
2026-10-28-work-assistant-mcp.md
2026-10-29-work-assistant-youtrack-fill.md
2026-10-30-mcp-only-cleanup.md
2026-10-30-youtrack-to-redmine-transfer.md
```

- [ ] **Step 5: Run the suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass (docs changes do not affect tests).

- [ ] **Step 6: Commit**

Run:

```bash
git add -A
git commit -m "docs: remove non-MCP plans and specs"
```

---

### Task 5: Rewrite Operator Docs and Run the Final Audit

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: MCP-only code from Tasks 1–4.
- Produces: MCP-only operator documentation and a clean final verification record.

- [ ] **Step 1: Replace `README.md`**

Write exactly:

````markdown
# Work Assistant

Локальный MCP-сервер для учёта времени. Он читает worklog'и Redmine и
YouTrack, git-коммиты, готовит планы и пишет часы только после подтверждения
через MCP elicitation. GUI и отдельного CLI-режима нет: единственный
поддерживаемый интерфейс — MCP stdio.

## Установка

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# заполните REDMINE_BASE_URL и YOUTRACK_BASE_URL
cp config/users.example.json config/users.json
chmod 600 config/users.json
# заполните токены и идентификаторы в config/users.json
```

`config/users.json` содержит токены, исключён из Git и должен иметь права
`600`. Один элемент массива `users` — один профиль:

- `name`, `is_enable`;
- `git_email` — автор коммитов для `get_git_commits`;
- `redmine.api_key`, `redmine.user_id`, `redmine.activity_id`,
  `redmine.comment`;
- `youtrack.access_token`;
- `youtrack.issue_id` — fallback issue для дозаполнения YouTrack;
- `youtrack.daily_meeting_issue_id`, `youtrack.daily_meeting_hours`.

AI-ключи не нужны: сервер не вызывает модели.

## Подключение к OpenCode

Проектный `.opencode/opencode.json` запускает сервер:

```json
{
  "mcp": {
    "servers": {
      "work-assistant": {
        "type": "local",
        "command": [".venv/bin/python", "-m", "mcp_server"],
        "cwd": ".",
        "codemode": false,
        "protocol": "legacy"
      }
    }
  }
}
```

Проверка:

```bash
opencode mcp list   # work-assistant connected
```

Ручной запуск:

```bash
.venv/bin/python -m mcp_server
```

## Tools

Сервер отдаёт ровно шесть tools, без prompts и resources:

| Tool | Назначение |
| --- | --- |
| `list_enabled_users` | имена включённых профилей и их трекеры |
| `get_worklogs` | worklogs профиля за период |
| `get_git_commits` | коммиты профиля за период |
| `prepare_youtrack_fill` | план дозаполнения YouTrack по коммитам |
| `prepare_youtrack_transfer` | план переноса YouTrack → Redmine |
| `write_plan` | запись плана после подтверждения |

Порядок: **read → prepare → `write_plan` approval**. `prepare_*` ничего не
пишет, возвращает `plan_id`, строки и warnings. `write_plan` показывает форму
подтверждения и выполняется только при явном `approved`. План одноразовый и
устаревает через 10 минут.

Период по умолчанию — с 1-го числа текущего месяца по сегодня.

### YouTrack fill

Issue задаётся на уровне строки плана: `DRIVEO-XXXX` берётся из тега в
subject/body коммита. Daily meeting использует
`youtrack.daily_meeting_issue_id` и `youtrack.daily_meeting_hours` (по
умолчанию `1.0`) в рабочие дни. `youtrack.issue_id` — fallback для дня без
коммитов. Часы положительные, кратны `0.5`, сумма с уже записанными за день не
больше 8. Даты work item'ов пишутся по UTC-полуночи.

### Перенос YouTrack → Redmine

`prepare_youtrack_transfer(user_name, issue_id, start, end)` читает worklog'и
YouTrack, суммирует часы по датам и готовит одну запись Redmine на дату в
указанный `issue_id`. `issue_id` обязателен в каждом вызове и не берётся из
JSON. Комментарий всегда равен `redmine.comment` (например, `development`);
задачи YouTrack в комментарий не попадают. Старые Redmine-записи этого
пользователя за даты источника удаляются после подтверждения и заменяются одной
новой записью; даты без worklog'ов YouTrack не трогаются.

Удаление и создание не транзакционны: если удаление прошло, а создание упало,
старая запись уже потеряна; результат помечается `failed` с `create_failed`.

## Новый трекер

1. Создайте `trackers/<kind>.py` с классом-наследником `BaseTracker` и
   декоратором `@register_tracker`.
2. Задайте `kind`, `label`, при необходимости `can_write = True`.
3. Реализуйте `get_worklogs(start, end)` и, для записи,
   `create_worklogs(records)`.
4. Импортируйте модуль в `trackers/__init__.py`, чтобы он зарегистрировался.

MCP-конфиг валидируется в `mcp_server/tracker_access.py`; GUI-полей и форм
больше нет.

## Тесты

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```
````

- [ ] **Step 2: Replace `AGENTS.md`**

Write exactly:

````markdown
# AGENTS.md

This file provides guidance for agents working on this codebase.

## Project Overview

Work Assistant is a local MCP stdio server for time tracking. It reads worklogs
from Redmine and YouTrack and commits from git, builds write plans, and writes
hours only after explicit MCP elicitation approval. GUI and CLI entry points
have been removed; MCP is the only supported interface. It uses:

- `mcp` for the local stdio server;
- `requests` for sync HTTP requests;
- `python-dotenv` for environment variables.

## Project Structure

```text
fill_redmine/
├── mcp_server/              # Local stdio MCP server
│   ├── __main__.py          # `python -m mcp_server`
│   ├── app.py               # create_server: tool registration
│   ├── config.py            # JSON user profiles (config/users.json)
│   ├── user_tools.py        # list_enabled_users
│   ├── read_tools.py        # get_worklogs, get_git_commits
│   ├── tracker_access.py    # profile -> tracker construction
│   ├── youtrack_tools.py    # prepare_youtrack_fill
│   ├── transfer_tools.py    # prepare_youtrack_transfer
│   ├── periods.py           # period parsing
│   ├── plans.py             # one-time write plans
│   ├── write_tools.py       # write_plan approval gate
│   └── writer.py            # approved plan execution
├── clients/                 # HTTP and git clients
│   ├── redmine_client.py
│   ├── youtrack_client.py
│   └── git_client.py
├── configs/config.py        # REDMINE_BASE_URL / YOUTRACK_BASE_URL
├── dto/                     # GitCommitDTO, WorklogDTO
├── trackers/                # BaseTracker + Redmine/YouTrack adapters
├── config/
│   ├── users.example.json
│   └── users.json           # ignored, 0600, real tokens
└── tests/                   # pytest suite
```

## Build/Run Commands

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
cp config/users.example.json config/users.json
chmod 600 config/users.json
```

Fill `REDMINE_BASE_URL`, `YOUTRACK_BASE_URL`, and the profile tokens in
`config/users.json`.

### Running the MCP server

```bash
.venv/bin/python -m mcp_server
```

OpenCode starts it automatically from `.opencode/opencode.json`. Verify with
`opencode mcp list` (expect `work-assistant connected`).

### Testing

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/pytest tests/test_mcp_server.py -v
.venv/bin/pytest -k "mcp"
```

### Linting and Formatting

The project has no linting configuration. If ruff is added:

```bash
ruff check .
ruff format .
```

## Code Style Guidelines

### Imports

Use absolute imports and order stdlib → third-party → local project:

```python
import os

from dotenv import load_dotenv

from configs.config import Config
from dto.worklog_dto import WorklogDTO
```

### Type Annotations

Use type hints for parameters and return types. Prefer built-in types and `|`
unions (Python 3.10+).

```python
def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
    ...

def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
    ...
```

### Naming

- Classes: PascalCase
- Functions/variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Private methods: `_prefix`

### Dataclasses

Use `@dataclass` for DTOs and plans.

### Error Handling

Use specific exceptions, `response.raise_for_status()` or explicit status
checks, and never include tokens or authorization headers in messages.

### User-Facing Strings

MCP tool results and approval text are mostly Russian; technical identifiers
stay in English.

### Formatting

Use f-strings, 4 spaces, max 100 characters per line.

## MCP Server

`mcp_server/` exposes exactly six tools and no prompts/resources:

- `list_enabled_users` — enabled profile names and tracker kinds;
- `get_worklogs` — worklogs for one profile and period;
- `get_git_commits` — commits for one profile and period;
- `prepare_youtrack_fill` — builds a per-issue YouTrack plan, never writes;
- `prepare_youtrack_transfer` — builds a YouTrack → Redmine plan, never writes;
- `write_plan` — executes a plan only after explicit elicitation approval.

Flow is read → prepare → `write_plan` approval. Plans are one-time, in-memory
and expire after 10 minutes. Missing approval, unknown/replayed/expired plans
and clients without elicitation support return `{"status": "blocked"}`.

YouTrack fill rules:

- Period defaults to the 1st of the current month through today.
- Issue is per entry (`DRIVEO-XXXX` from commit subject/body). If no referenced
  commit mentions the issue, the plan is created with a warning.
- Daily meeting uses `youtrack.daily_meeting_issue_id` for
  `youtrack.daily_meeting_hours` (default `1.0`) on Mon–Fri.
- `youtrack.issue_id` is the fallback for stretching a day to 8 hours when
  there are no commits.
- Hours are positive multiples of `0.5`; proposed plus existing daily hours
  must not exceed 8.
- YouTrack work item dates use UTC midnight.

YouTrack → Redmine transfer rules:

- `prepare_youtrack_transfer` accepts a required positive Redmine `issue_id`;
  the ID is never read from JSON or SQLite.
- Period defaults to the 1st of the current month through today.
- Worklogs are summed per date; one Redmine entry is created per date.
- The Redmine comment is exactly `redmine.comment`; source issue IDs are never
  appended.
- For every source date, all of the user's existing Redmine time entries are
  recorded and deleted after approval, then replaced by the new entry. Dates
  without YouTrack worklogs are left untouched.
- `prepare_youtrack_transfer` performs no POST/DELETE. `write_plan` performs
  all deletions and creations only after explicit approval.
- If deletion fails for a date, no new entry is created for that date; other
  dates still proceed.
- Deletion and creation are not transactional: if deletion succeeds but
  creation fails, the old entry is already gone; the result is marked `failed`
  with `create_failed`.

Security rules:

- `config/users.json` holds tokens, is git-ignored and must stay `0600`. Only
  `config/users.example.json` with blank placeholders is tracked.
- Tool output, errors and logs must never contain access tokens, API keys or
  authorization headers.
- Tests use in-memory MCP clients, fakes and Git fixtures; they must not make
  live tracker requests or write to real trackers.

## Environment Variables

Required:

- `REDMINE_BASE_URL` — Redmine instance URL;
- `YOUTRACK_BASE_URL` — YouTrack instance URL.

Tracker keys and models are not read from env. The MCP server reads profiles
and tokens from `config/users.json`.

## Making Changes

1. Run `.venv/bin/pytest -q`.
2. Update the MCP tests when changing tool contracts.
3. Keep the catalog at six tools, no prompts/resources/instructions.
4. Each task ends with green tests and its own commit.
````

- [ ] **Step 3: Replace `.env.example`**

Write exactly:

```dotenv
REDMINE_BASE_URL=https://redmine.org
YOUTRACK_BASE_URL=https://youtrack.cloud
```

- [ ] **Step 4: Audit removed packages**

Run:

```bash
rg -n "from gui|import gui|from services|import services|from storage|import storage|clients\.ai|configs\.ai_settings|configs\.project_config|configs\.user_config|dto\.tracking_dto|dto\.commit_plan_dto|work_assistant\.py|fill_redmine_gui|run_gui" --glob '!docs/**' --glob '!.superpowers/**' --glob '!.venv/**' .
```

Expected: no matches (ripgrep exit status 1).

- [ ] **Step 5: Verify MCP starts**

Run:

```bash
timeout 3 .venv/bin/python -m mcp_server
```

Expected: timeout exit code `124` (server waits for stdio). If it exits 0 or 1
immediately, report the error.

- [ ] **Step 6: Verify local data was not changed**

Run:

```bash
sha256sum -c /tmp/opencode/preserve-before.sha256
```

Expected:

```text
.env: OK
config/users.json: OK
work_assistant.db: OK
user_list.py.migrated: OK
```

- [ ] **Step 7: Run the full suite and whitespace check**

Run:

```bash
.venv/bin/pytest -q
git diff --check
```

Expected: all tests pass; `git diff --check` prints nothing.

- [ ] **Step 8: Commit**

Run:

```bash
git add -A
git commit -m "docs: document MCP-only operation"
```

---

### Final Gate: Whole-Branch Review

After Task 5, dispatch one final code reviewer over the whole cleanup range.
The review must confirm:

- no GUI/CLI/storage/services/AI code or tests remain;
- MCP catalog is still exactly six tools;
- `.env`, `config/users.json`, database and migrated user data are untouched;
- README/AGENTS describe only MCP operation;
- the remaining test suite is green.