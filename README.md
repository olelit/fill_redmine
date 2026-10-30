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
