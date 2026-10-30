# Дизайн: MCP-only cleanup

Дата: 2026-10-30  
Статус: согласован в диалоге; ожидает review письменной спецификации

## Цель

Оставить в проекте только локальный MCP-сервер и код, который ему нужен для
чтения/записи worklog'ов. Удалить GUI, CLI-запуск, SQLite/storage-слой,
services, AI-клиенты, legacy-конфиги, их тесты, лаунчеры и документацию.

Эта спецификация расширяет и заменяет `2026-10-28-work-assistant-gui-removal-design.md`:
удаляется не только GUI, но и весь неиспользуемый backend.

## Согласованные решения

| Тема | Решение |
| --- | --- |
| Единственный интерфейс | MCP stdio-сервер (`python -m mcp_server`) |
| GUI | Удалить полностью |
| CLI-запуск | Удалить; остаётся только запуск MCP-сервера |
| Storage/SQLite | Удалить код; локальные файлы данных не трогать |
| AI-клиенты | Удалить |
| Legacy-конфиги/DTO | Удалить, если MCP их не импортирует |
| Документация | Оставить только MCP-спеки и планы |
| Локальные данные | Сохранить без изменений |
| Git-история | Не переписывать |

## Что остаётся

```text
mcp_server/                         # MCP stdio server и его tools
clients/git_client.py               # git log для get_git_commits
clients/redmine_client.py           # Redmine time entries
clients/youtrack_client.py          # YouTrack work items
configs/config.py                   # REDMINE_BASE_URL / YOUTRACK_BASE_URL
dto/git_commit_dto.py
dto/worklog_dto.py
trackers/base.py, registry.py, redmine.py, youtrack.py, __init__.py
config/users.example.json
.env.example
.opencode/opencode.json
pytest.ini
requirements.txt
requirements-dev.txt
README.md
AGENTS.md
docs/superpowers/specs/2026-10-28-work-assistant-mcp-design.md
docs/superpowers/specs/2026-10-30-youtrack-to-redmine-transfer-design.md
docs/superpowers/plans/2026-10-28-work-assistant-mcp.md
docs/superpowers/plans/2026-10-29-work-assistant-youtrack-fill.md
docs/superpowers/plans/2026-10-30-youtrack-to-redmine-transfer.md
tests/conftest.py
tests/test_git_client.py
tests/test_mcp_config.py
tests/test_mcp_read_tools.py
tests/test_mcp_server.py
tests/test_mcp_transfer_tools.py
tests/test_mcp_write_tools.py
tests/test_mcp_youtrack_tools.py
tests/test_redmine_tracker.py
tests/test_youtrack_tracker.py
tests/test_tracker_registry.py
```

## Что удаляется

### Runtime

```text
gui/
services/
storage/
clients/ai/
configs/ai_settings.py
configs/iterable_config_dto.py
configs/project_config.py
configs/user_config.py
dto/commit_plan_dto.py
dto/tracking_dto.py
work_assistant.py
fill_redmine_gui.py
run_gui.sh
Work Assistant.desktop
scripts/install_desktop.sh
assets/work_assistant.svg
DTD XHTML
```

### Тесты

Удалить тесты, которые проверяют только GUI, storage, migrations, AI,
tracking service или legacy user config:

```text
tests/test_ai_providers.py
tests/test_ai_settings_validation.py
tests/test_database.py
tests/test_gui_formatting.py
tests/test_gui_validation.py
tests/test_gui_worker.py
tests/test_migration.py
tests/test_migration_v2.py
tests/test_project_migration.py
tests/test_project_repository.py
tests/test_report_editor_validation.py
tests/test_settings_repository.py
tests/test_settings_validation.py
tests/test_tracking_service.py
tests/test_tracking_validation.py
tests/test_tracking_write.py
tests/test_user_config.py
tests/test_user_repository.py
```

### Документация

Удалить старые спеки/планы, не относящиеся к MCP:

```text
docs/superpowers/specs/2026-10-06-gui-sqlite-users-design.md
docs/superpowers/specs/2026-10-26-work-assistant-projects-design.md
docs/superpowers/specs/2026-10-27-work-assistant-tracking-redesign.md
docs/superpowers/specs/2026-10-28-work-assistant-gui-removal-design.md
docs/superpowers/plans/2026-10-06-gui-sqlite-users.md
docs/superpowers/plans/2026-10-26-work-assistant-projects.md
docs/superpowers/plans/2026-10-27-work-assistant-tracking-v2.md
docs/superpowers/plans/2026-10-28-work-assistant-gui-removal.md
```

## Очистка MCP-ядра от GUI-хвостов

`trackers/base.py`:

- удалить `TrackerField`, `fields`, `can_read`, `is_configured` и
  `validate_config`;
- оставить `BaseTracker` с `kind`, `label`, `can_write`, `config`,
  абстрактным `get_worklogs` и `create_worklogs` (по умолчанию — ошибка);
- `TrackerField` больше не нужен: MCP-конфиг валидируется в
  `mcp_server/tracker_access.py`.

`trackers/registry.py`:

- оставить только `register_tracker`, `get_tracker_class` и внутренний реестр;
- удалить `all_trackers`, `build_tracker` и `configured_trackers`;
- удалить импорт `configs.project_config`.

`trackers/redmine.py`, `trackers/youtrack.py`:

- удалить `fields` и импорт `TrackerField`;
- оставить `kind`, `label`, `can_write`, `get_worklogs`, `create_worklogs`.

`trackers/__init__.py`:

- оставить импорт `BaseTracker`, `get_tracker_class`, `register_tracker` и
  регистрацию конкретных трекеров;
- удалить экспорты GUI-хелперов.

`clients/git_client.py`:

- удалить `get_config_email` (использовался только GUI);
- `validate` и `list_commits` оставить: `list_commits` вызывает `validate`.

`tests/test_tracker_registry.py`:

- удалить тесты `configured_trackers`, `is_configured`, `validate_config`;
- оставить проверки регистрации, дубликата и `get_tracker_class`.

`tests/test_redmine_tracker.py`, `tests/test_youtrack_tracker.py`:

- удалить тесты `is_configured`; остальные тесты MCP-путей оставить.

`tests/test_git_client.py`:

- удалить тест `get_config_email`; тесты `validate` и `list_commits` оставить.

## Документация

`README.md` переписать под MCP-only:

- что это локальный MCP-сервер;
- установка venv и зависимостей;
- `.env` с `REDMINE_BASE_URL` и `YOUTRACK_BASE_URL`;
- `config/users.json` (0600, git-ignored);
- подключение к OpenCode;
- шесть tools и порядок read → prepare → `write_plan` approval;
- YouTrack fill и YouTrack → Redmine transfer;
- как добавить трекер;
- тесты.

Удалить из README все разделы про GUI, KDE-ярлык, проекты, SQLite, AI,
миграции и `WORK_ASSISTANT_DB`.

`AGENTS.md` переписать:

- project overview — только MCP;
- project structure — только оставшиеся модули;
- build/run — venv, `.env`, `config/users.json`, `python -m mcp_server`,
  pytest;
- env vars — только `REDMINE_BASE_URL`, `YOUTRACK_BASE_URL`;
- MCP server rules и security rules сохранить/актуализировать;
- удалить GUI/AI/storage/services/migrations.

`.env.example`:

```dotenv
REDMINE_BASE_URL=https://redmine.org
YOUTRACK_BASE_URL=https://youtrack.cloud
```

Удалить `WORK_ASSISTANT_DB`.

## Что сохраняется без изменений

- `.env` — реальные URL, не перезаписывать.
- `config/users.json` — реальные токены, 0600, git-ignored.
- `work_assistant.db`, `user_list.py.migrated` — локальные legacy-данные,
  не удалять и не изменять.
- `.git` и история коммитов.

`.gitignore` может сохранять ignore-правила для этих локальных файлов, даже
если GUI больше нет: это защита от случайного коммита пользовательских данных.

## Проверки

1. `pytest -q` — зелёный только по MCP-ядру и его зависимостям.
2. `pytest --collect-only` не импортирует удалённые модули.
3. Поиск ссылок на удалённые пакеты не находит совпадений в оставшемся коде:
   `gui`, `services`, `storage`, `clients.ai`, `configs.ai_settings`,
   `configs.project_config`, `configs.user_config`, `dto.tracking_dto`,
   `dto.commit_plan_dto`, `work_assistant`, `fill_redmine_gui`, `run_gui`.
4. `timeout 3 .venv/bin/python -m mcp_server` запускается и ждёт stdio
   (код выхода 124 от timeout — нормально).
5. Каталог MCP — ровно шесть tools без prompts/resources/instructions
   (существующий тест).
6. Хэши `.env`, `config/users.json`, `work_assistant.db`,
   `user_list.py.migrated` совпадают с значениями до cleanup.
7. `git diff --check` чистый.

## Вне рамок

- Переписывание git-истории.
- Удаление локальных данных и токенов.
- Изменение MCP-сценариев, tool-контрактов и правил записи.
- Переход на другой MCP SDK или транспорт.
- Автоматический `git push`.