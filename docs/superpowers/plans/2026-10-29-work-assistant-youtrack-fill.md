# Work Assistant YouTrack Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development`
> to implement this plan task-by-task. A fresh subagent per task, a task review
> after each, and a broad final review are mandatory.

**Goal:** Заполнить YouTrack work items по git-коммитам за текущий месяц:
распределить дефицит до 8 часов в день по issue из тегов `DRIVEO-XXXX`,
добавить daily meeting 1 час на каждый рабочий день и записать всё только
после явного подтверждения через MCP elicitation.

**Architecture:** Продолжаем ветку `feature/work-assistant-mcp`. Задачи 1–4
уже реализованы: JSON-профили, stdio-сервер, read-only tools, планы и
fail-closed `write_plan`. В этой фазе добавляем per-issue модель плана,
чтение YouTrack work items с issue, `prepare_youtrack_fill` и проектную
MCP-конфигурацию. Redmine-сценарии (Tasks 5–6 старого плана) не входят в
эту фазу.

**Tech Stack:** Python 3.10+, `mcp>=2.3,<3`, `requests`, существующие
`GitClient`/`YoutrackTracker`, pytest, OpenCode V2 local MCP.

## Global Constraints

- Работаем в ветке `feature/work-assistant-mcp`; задачи 1–4 уже в истории.
- Redmine autofill и YouTrack→Redmine в эту фазу не входят.
- YouTrack issue задаётся на уровне строки плана, а не один на весь план.
- Daily meeting: 1 час на `youtrack.daily_meeting_issue_id` в каждый рабочий
  день, если он ещё не записан; строке daily meeting не нужны commit hashes.
- `prepare_youtrack_fill` не делает POST и не вызывает AI. Запись — только
  через `write_plan` и обязательный elicitation.
- Комментарии, часы и issue показываются в approval как читаемый текст,
  сгруппированный по датам; переводы строк и `|` в комментариях заменяются,
  чтобы не spoof-ить строки.
- MCP-ответы и логи не содержат токены, API-ключи и authorization headers.
- Коммиты проверяются через `GitClient` по профилю (`git_email`) и периоду;
  issue должен встречаться в subject/body хотя бы одного переданного коммита.
  Если issue не найден — warning, а не ошибка (нужно для no-tag дней).
- Часы: положительные, кратны 0.5; сумма за день с уже записанными ≤ 8.
- Период по умолчанию: с 1-го числа текущего месяца по сегодня.
- Тесты не делают live HTTP-запросов и не пишут в трекеры.
- Каждая задача заканчивается зелёными тестами и отдельным коммитом.

---

## Task 1: Read and write YouTrack worklogs per issue

**Files:**
- Modify: `trackers/youtrack.py`
- Modify: `mcp_server/tracker_access.py`
- Modify: `tests/test_youtrack_tracker.py`
- Modify: `tests/test_mcp_read_tools.py`

**Interfaces:**
- `YoutrackTracker.get_worklogs(start, end)` агрегирует минуты по
  `(date, issue)` и возвращает `WorklogDTO(date, hours, issue=..., source="youtrack")`.
  Если у work item нет issue, issue остаётся `""`.
- `build_user_tracker(profile, kind, *, issue_id: int | str | None = None, for_write=False)`
  - для `youtrack` при чтении требует только `access_token`;
  - для `youtrack` при записи требует непустой `issue_id` (строка) и
    подставляет его в `config["issue_id"]`;
  - для `redmine` поведение не меняется: issue обязателен только для записи.
- Не менять `YoutrackTracker.fields`: GUI пока продолжает требовать issue_id
  в настройках; MCP использует `build_user_tracker` напрямую.

- [ ] **Step 1: Add failing tests**

В `tests/test_youtrack_tracker.py`:
- добавить тест, где два work item за один день относятся к разным issue;
  ожидать две строки с датой, часами и issue;
- существующий тест агрегации без issue должен остаться зелёным.

В `tests/test_mcp_read_tools.py`:
- YouTrack-профиль без `issue_id` читает worklogs (только `access_token`);
- результат содержит issue из JSON;
- `build_user_tracker(profile, "youtrack", issue_id="DRIVEO-1", for_write=True)`
  подставляет issue;
- запись без issue даёт `ProfileConfigError`.

- [ ] **Step 2: Run focused tests and confirm failure**

Run:
`.venv/bin/python -m pytest tests/test_youtrack_tracker.py tests/test_mcp_read_tools.py -q`

Expected: новые тесты падают; старые проходят.

- [ ] **Step 3: Implement**

`trackers/youtrack.py`:
- заменить `by_date` на `by_key: dict[tuple[str, str], float]`;
- issue брать из `item.get("issue", {}).get("idReadable")`;
- сортировать по `(date, issue)`.

`mcp_server/tracker_access.py`:
- `issue_id` принимает `int | str | None`;
- `required` для YouTrack — `["access_token"]`;
- при `for_write and kind == "youtrack"` требовать непустую строку issue;
- при `for_write and kind == "redmine"` оставить int > 0;
- не подставлять issue в read-конфиг.

- [ ] **Step 4: Verify and commit**

Run:
`.venv/bin/python -m pytest tests/test_youtrack_tracker.py tests/test_mcp_read_tools.py -q`
`.venv/bin/python -m pytest -q`

Expected: всё зелёное, без warning'ов.

Commit: `feat: read and write YouTrack worklogs per issue`.

---

## Task 2: Per-entry issue plans, approval and writer

**Files:**
- Modify: `mcp_server/plans.py`
- Modify: `mcp_server/write_tools.py`
- Modify: `mcp_server/writer.py`
- Modify: `tests/test_mcp_write_tools.py`

**Interfaces:**
- `PlannedEntry(date, hours, comment, commit_hashes, issue_id: str = "")`.
- `PlanStore.create(...)` требует уникальности `(date, issue_id or plan.issue_id)`;
  две строки за одну дату с разными issue разрешены.
- `write_plan` approval message — читаемый текст, сгруппированный по датам:
  - заголовок, пользователь, трекер, число строк и сумма часов;
  - каждая строка: часы, issue (`entry.issue_id or plan.issue_id`), комментарий;
  - блок warnings;
  - переводы строк и `|` в комментариях заменяются, чтобы не spoof-ить строки;
  - никаких токенов.
- `execute_plan(plan, users_path)`:
  - Redmine: как раньше, один issue на план, records с `issue=plan.issue_id`;
  - YouTrack: сгруппировать entries по `entry.issue_id or plan.issue_id`,
    для каждой группы построить tracker с этим issue, записать пачкой;
  - ошибка одной группы не должна мешать другим группам;
  - результат: `{"results": [{"date": ..., "issue": ..., "status": "created"|"failed"}]}`.
- При пустом issue у YouTrack-строки — `ProfileConfigError` до любых записей.

- [ ] **Step 1: Add failing tests**

В `tests/test_mcp_write_tools.py`:
- `PlanStore` принимает две строки одной даты с разными issue и отвергает
  дубль `(date, issue)`;
- approval-текст содержит issue каждой строки и warnings, не содержит токен;
- writer для двух issue вызывает два tracker'а, возвращает статусы по каждой
  строке; падение одного не отменяет второй;
- Redmine-план продолжает работать;
- старый тест про проверку одного текущего YouTrack issue заменить на
  per-issue группировку: single-issue проверка больше не нужна.

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_write_tools.py -q`

Expected: новые тесты падают.

- [ ] **Step 3: Implement**

В `plans.py` — новое поле и проверка уникальности.
В `write_tools.py` — читаемый текст с issue и warnings и санитайзингом
пользовательских комментариев.
В `writer.py` — группировка YouTrack по issue, `build_user_tracker(...,
issue_id=issue, for_write=True)`, per-group ошибки.

- [ ] **Step 4: Verify and commit**

Run:
`.venv/bin/python -m pytest tests/test_mcp_write_tools.py -q`
`.venv/bin/python -m pytest -q`

Commit: `feat: write YouTrack plans per issue`.

---

## Task 3: `prepare_youtrack_fill` from commits

**Files:**
- Create: `mcp_server/youtrack_tools.py`
- Create: `tests/test_mcp_youtrack_tools.py`
- Modify: `mcp_server/app.py`
- Modify: `tests/test_mcp_server.py` (add the new tool to the catalog so the suite stays green; Task 4 finalizes docs/config)

**Interfaces:**
- `SuggestedEntry` (Pydantic `BaseModel`):
  `date: str`, `issue_id: str`, `hours: float`, `comment: str`,
  `commit_hashes: list[str]`.
- `register_youtrack_tools(server: MCPServer, users_path: Path, plans: PlanStore) -> None`
  регистрирует `prepare_youtrack_fill`.
- `prepare_youtrack_fill(user_name: str, repo_path: str, entries: list[SuggestedEntry],
  start: str | None = None, end: str | None = None) -> dict[str, object]`:
  - по умолчанию `start` — 1-е число текущего месяца, `end` — сегодня;
  - читает профиль, коммиты через `GitClient(repo_path)` и worklogs YouTrack;
  - создаёт план, не пишет и не вызывает AI;
  - возвращает `status`, `plan_id`, `user`, `period`, `entries`, `warnings`.
- Daily meeting:
  - `youtrack.daily_meeting_issue_id` и `youtrack.daily_meeting_hours`
    (default 1.0);
  - для daily meeting разрешены пустые `commit_hashes`, но только если issue
    совпадает, часы равны настройке и дата — рабочий день (Mon–Fri);
  - если на эту дату уже есть worklog на `daily_meeting_issue_id`, строка
    отклоняется как дубль;
  - если daily meeting не настроен, строки без `commit_hashes` отклоняются;
  - для остальных строк `commit_hashes` обязательны.
- Ошибки конфигурации и валидации возвращаются как MCP `ToolError` с
  безопасным текстом без токенов.
- Валидация:
  - дата в периоде, ISO `YYYY-MM-DD`;
  - issue `^[A-Z][A-Z0-9]+-\d+$` после `strip().upper()`;
  - часы > 0, кратны 0.5;
  - комментарий не пустой;
  - каждый hash существует у автора и относится к дате строки;
  - issue встречается в subject/body хотя бы одного из переданных коммитов;
    иначе warning `"<date>: issue <ID> not found in commit subjects"`;
  - дубликаты `(date, issue)` запрещены;
  - сумма proposed + existing за день ≤ 8.
- `app.create_server` регистрирует tool до `write_plan`; порядок каталога:
  `list_enabled_users`, `get_worklogs`, `get_git_commits`,
  `prepare_youtrack_fill`, `write_plan`.

- [ ] **Step 1: Add failing tests**

В `tests/test_mcp_youtrack_tools.py` через in-memory MCP client и monkeypatch
`GitClient`/`build_user_tracker`:
- валидный план: две строки одной даты с разными issue, existing 1 ч,
  proposed 7 ч, plan создан, `create_worklogs` не вызван;
- issue из коммита и issue, которого нет в тегах (warning);
- daily meeting без hashes принимается при корректной настройке;
- ошибки: нет коммитов, чужой hash, hash другой даты, часы не кратны 0.5,
  сумма > 8, дубль date+issue, пустой комментарий, daily meeting с неверными
  часами/в выходной;
- период по умолчанию (можно проверить через явные `start`/`end` и отдельный
  тест на helper текущего месяца);
- в результате нет токена.

- [ ] **Step 2: Run focused test and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_youtrack_tools.py -q`

Expected: `ModuleNotFoundError` или отсутствующий tool.

- [ ] **Step 3: Implement**

Создать `mcp_server/youtrack_tools.py`, зарегистрировать в `app.py`.
Использовать существующие `GitClient`, `build_user_tracker`,
`fingerprint_target_config` и `PlanStore`.

- [ ] **Step 4: Verify and commit**

Run:
`.venv/bin/python -m pytest tests/test_mcp_youtrack_tools.py -q`
`.venv/bin/python -m pytest -q`

Commit: `feat: prepare per-issue YouTrack fill from commits`.

---

## Task 4: Project MCP config, catalog and docs

**Files:**
- Modify: `.opencode/opencode.json`
- Modify: `config/users.example.json`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_mcp_server.py`
- Modify: `mcp_server/youtrack_tools.py` (Task 3 review nits: trailing newline,
  remove dead `today` parameter, add parameter type annotations)
- Modify: `tests/test_mcp_youtrack_tools.py` (trailing newline)

**Interfaces:**
- `.opencode/opencode.json` запускает `.venv/bin/python -m mcp_server`
  с `cwd: "."`, `codemode: false`, `protocol: legacy`.
- `config/users.example.json` показывает:
  - `git_email`;
  - `youtrack.access_token`;
  - `youtrack.daily_meeting_issue_id`;
  - `youtrack.daily_meeting_hours`;
  - `youtrack.issue_id` остаётся опциональным fallback.
- Catalog test ожидает ровно пять tools:
  `list_enabled_users`, `get_worklogs`, `get_git_commits`,
  `prepare_youtrack_fill`, `write_plan`; prompts/resources пустые.
- README и AGENTS описывают локальный MCP, `config/users.json` (ignored,
  `0600`), сценарий YouTrack fill, daily meeting и обязательный approval.
  README должен явно указать:
  - `pip install -r requirements.txt`, `.env` с `YOUTRACK_BASE_URL`;
  - `cp config/users.example.json config/users.json`, `chmod 600`;
  - запуск через OpenCode, `opencode mcp list`;
  - пять tools и порядок «read → prepare → write_plan approval»;
  - период по умолчанию — текущий месяц по сегодня;
  - per-issue из `DRIVEO-XXXX`, warning для no-tag коммитов;
  - daily meeting 1 ч на рабочий день, если ещё не записан;
  - Redmine-сценарии в этой фазе не реализованы;
  - AI-ключи серверу не нужны.
- Реальный `config/users.json` с токеном создаёт контроллер после задачи;
  в репозиторий он не попадает.

- [ ] **Step 1: Update failing catalog/config tests**

Обновить `tests/test_mcp_server.py` под пять tools и проверить, что
`create_server` не отдаёт prompts/resources/instructions.

- [ ] **Step 2: Run focused test and confirm failure**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`

Expected: падает на старом списке tools.

- [ ] **Step 3: Update config and docs**

Обновить `.opencode/opencode.json`, `config/users.example.json`, README,
AGENTS. Не добавлять реальные секреты.

- [ ] **Step 4: Verify and commit**

Run:
`.venv/bin/python -m pytest tests/test_mcp_server.py -q`
`.venv/bin/python -m pytest -q`
`git diff --check`

Commit: `docs: document per-issue YouTrack MCP setup`.

---

## Post-plan: Live fill (controller, not a subagent)

1. Создать `config/users.json` с правами `0600`:
   Oleg, `oleg.litasov@dynevo.org`, YouTrack token из существующего
   `driveo/.opencode.json`, `daily_meeting_issue_id = "DRIVEO-2542"`,
   `daily_meeting_hours = 1.0`. Файл ignored, не коммитить.
2. `opencode mcp list` → `work-assistant connected`.
3. Read-only: `get_worklogs` и `get_git_commits` за `2026-10-01..2026-10-29`.
4. Собрать недельные entries:
   - daily meeting 1 ч на каждый рабочий день, если ещё не записан;
   - task hours — дефицит до 8 ч, распределённый по issue из коммитов;
   - no-tag дни (22, 23, 28 октября) — предложить маппинг и показать warning.
5. `prepare_youtrack_fill` по неделям; показать план.
6. `write_plan` только после approval; проверить `get_worklogs`.
7. Не делать live write в тестах; только после явного подтверждения формы.