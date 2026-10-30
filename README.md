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
- `youtrack.project_keys` — необязательный список префиксов проектов в верхнем
  регистре, например `["DRIVEO"]`; добавляет распознавание этих проектов в
  любом регистре (теги в верхнем регистре распознаются всегда);
- `youtrack.issue_id` — fallback issue для дозаполнения YouTrack;
- `youtrack.daily_meeting_issue_id`, `youtrack.daily_meeting_hours`;
- `youtrack.workday_start` — начало рабочего дня, по умолчанию `09:00`;
- `youtrack.default_comment` — комментарий fallback-записи, по умолчанию
  `development`.

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

Сервер отдаёт ровно семь tools, без prompts и resources:

| Tool | Назначение |
| --- | --- |
| `list_enabled_users` | имена включённых профилей и их трекеры |
| `get_worklogs` | worklogs профиля за период |
| `get_git_commits` | коммиты профиля за период |
| `prepare_youtrack_fill` | план дозаполнения YouTrack по коммитам |
| `prepare_youtrack_from_commits` | план дня по коммитам, по умолчанию сегодня |
| `prepare_youtrack_transfer` | план переноса YouTrack → Redmine |
| `write_plan` | запись плана после подтверждения |

Порядок: **read → prepare → `write_plan` approval**. `prepare_*` ничего не
пишет, возвращает `plan_id`, строки и warnings. `write_plan` показывает форму
подтверждения и выполняется только при явном `approved`. План одноразовый и
устаревает через 10 минут.

### YouTrack fill

Период по умолчанию — с 1-го числа текущего месяца по сегодня.

Issue задаётся на уровне строки плана: `DRIVEO-XXXX` берётся из тега в
subject/body коммита. Daily meeting использует
`youtrack.daily_meeting_issue_id` и `youtrack.daily_meeting_hours` (по
умолчанию `1.0`) в рабочие дни. `youtrack.issue_id` — fallback для дня без
коммитов. Часы положительные, кратны `0.5`, сумма с уже записанными за день не
больше 8. Даты work item'ов пишутся по UTC-полуночи.

### Трекинг дня по коммитам

`prepare_youtrack_from_commits(user_name, repo_path, start, end, daily_hours)`
строит план YouTrack из git-коммитов. Без `start` и `end` берётся только
сегодня; период односторонний: только `start` — с этой даты по сегодня, только
`end` — ровно этот день. `end` в будущем отклоняется. `daily_hours` по
умолчанию `8.0` и должен быть положительным, не больше 8.

Для каждого дня:

1. Из целевых часов вычитаются уже записанные за этот день часы YouTrack.
   Дробный остаток округляется вниз до кратного `0.5` с warning.
2. Daily meeting добавляется отдельной записью, если он настроен, день рабочий
   и ещё не записан; его часы вычитаются из остатка.
3. Остаток распределяется по issue из subject/body коммитов пропорционально
   интервалам: вес коммита — время от предыдущего коммита (или от
   `youtrack.workday_start`) до текущего. Если issue в коммите несколько, вес
   делится между ними поровну.
4. Часы округляются до `0.5`, сумма равна доступному остатку. Комментарий —
   subject последнего коммита по issue.
5. Если коммитов нет или в них нет issue, используется `youtrack.issue_id` с
   комментарием `youtrack.default_comment`.

`youtrack.project_keys` — необязательный список префиксов проектов, например
`["DRIVEO"]`; только заглавные буквы (`DRIVEO`, не `driveo`). Тег issue в
верхнем регистре (`PROJ-42`) распознаётся всегда, для любого проекта, даже
если его префикса нет в списке. Префиксы из `youtrack.project_keys`,
`youtrack.issue_id` и `youtrack.daily_meeting_issue_id` дополнительно
включают распознавание этих проектов в любом регистре (`driveo-123` →
`DRIVEO-123`). Без `project_keys` распознаются только теги в верхнем регистре.

`prepare_*` ничего не пишет: запись выполняется только через `write_plan` после
подтверждения.

### Перенос YouTrack → Redmine

Период по умолчанию — с 1-го числа текущего месяца по сегодня.

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
