# Дизайн: Work Assistant — трекинг времени v2

Дата: 2026-10-27
Статус: утверждён

## Цель

Переделать Work Assistant из набора отдельных импортов в единый сценарий трекинга:

1. Главный экран — только список проектов, кнопки «Добавить» и «Удалить».
2. Внутри проекта — пункт меню «Трекинг времени».
3. В трекинге выбираются:
   - трекер-назначение (куда писать);
   - источник (автозаполнение / другой трекер / коммиты);
   - период;
   - юзеры (галочками).
4. Перед записью показывается редактируемый отчёт по дням.
5. Запись идёт в выбранный трекер от имени каждого выбранного юзера.

Дополнительно:

- в проекте может быть несколько юзеров, у каждого свои ключи, issue и email для коммитов;
- настройки проекта — панель сверху экрана трекинга, с импортом из другого проекта;
- глобальные настройки AI — провайдер и модель: OpenCode Go, OpenAI, Anthropic, Custom;
- CLI удаляется, остаётся только GUI.

## Ключевые решения

| Вопрос | Решение |
| --- | --- |
| Модель проекта | Проект + список юзеров; общие настройки проекта отдельно |
| Конфиги трекеров | JSON на каждого юзера, реестр трекеров |
| Назначение | Redmine или YouTrack, запись поддерживают оба |
| Источники | Автозаполнение, из другого трекера, из коммитов |
| Несколько юзеров | Галочки; отчёт и запись по каждому выбранному |
| Отчёт | Treeview + диалог редактирования строки, чекбокс включения |
| Комментарий | `development` по умолчанию; для коммитов — комментарий ИИ |
| AI | Глобальные настройки, провайдеры OpenCode Go / OpenAI / Anthropic / Custom |
| CLI | Удаляется |
| Старые данные | Миграция схемы v2, старые таблицы сохраняются |

## Архитектура

```
configs/
  project_config.py        # ProjectConfig + ProjectUserConfig
  ai_settings.py           # AiSettings, провайдеры
storage/
  database.py              # schema v2
  project_repository.py    # проекты + юзеры
  settings_repository.py   # глобальные AI-настройки
  migration.py             # user_list -> users -> projects -> project_users
trackers/
  base.py                  # чтение + запись worklog'ов
  redmine.py               # RedmineTracker (read/write)
  youtrack.py              # YoutrackTracker (read/write)
  registry.py              # регистрация и построение
clients/
  redmine_client.py        # чтение/запись time entries
  youtrack_client.py       # чтение/запись work items
  git_client.py            # коммиты по email/периоду
  ai/                      # провайдеры AI
    base.py
    openai_chat.py
    openai_responses.py
    anthropic_messages.py
    opencode_go.py
    registry.py
services/
  tracking_service.py      # отчёт по дням + запись
  commit_plan_service.py   # ИИ-план по коммитам (per user)
gui/
  app.py                   # главное окно
  project_list_view.py     # только список проектов
  project_view.py          # экран проекта + меню
  tracking_view.py         # трекинг
  project_settings_panel.py
  user_editor.py
  report_editor.py
  ai_settings_dialog.py
  worker.py
work_assistant.py          # единственная точка входа
fill_redmine_gui.py        # legacy-обёртка
```

Правила зависимостей:

- `gui → services → trackers/clients/storage`;
- трекеры не знают про GUI;
- TrackingService получает `ProjectConfig`, `ProjectUserConfig`, период, вид назначения и источника;
- новый трекер = модуль + регистрация, без миграции БД и правок GUI.

## Модель данных

### Проект

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    git_repo_path TEXT NOT NULL DEFAULT '',
    workday_hours REAL NOT NULL DEFAULT 8,
    exclude_dates TEXT NOT NULL DEFAULT '[]',
    default_comment TEXT NOT NULL DEFAULT 'development'
    -- legacy: git_author_email, trackers_json, ai_json остаются для миграции
);
```

`ProjectConfig`:

```python
@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    default_comment: str = "development"
    users: list[ProjectUserConfig] = field(default_factory=list)
    db_id: int | None = None
```

### Юзер проекта

```sql
CREATE TABLE project_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    git_email TEXT NOT NULL DEFAULT '',
    trackers_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, name)
);
```

`ProjectUserConfig`:

```python
@dataclass
class ProjectUserConfig:
    name: str
    git_email: str = ""
    trackers: dict[str, dict] = field(default_factory=dict)
    project_id: int | None = None
    db_id: int | None = None
```

`trackers_json`:

```json
{
  "redmine": {
    "api_key": "...",
    "user_id": 16,
    "activity_id": 9,
    "issue_id": 2682
  },
  "youtrack": {
    "access_token": "...",
    "issue_id": "PROJ-123"
  }
}
```

Поля задаются трекером через `TrackerField`; GUI рисует их автоматически.

### Глобальные настройки

```sql
CREATE TABLE app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Ключ `ai_settings` хранит JSON:

```json
{
  "provider": "opencode_go",
  "model": "deepseek-v4.1-flash",
  "base_url": "",
  "keys": {
    "opencode_go": "...",
    "openai": "...",
    "anthropic": "...",
    "custom": "..."
  }
}
```

Секреты — в SQLite открытым текстом, файл БД `600`, в UI маскируются.

### Репозитории

`ProjectRepository`:

- `list_projects()`, `get_project(db_id)`, `find_by_name(name)`;
- `add_project(project)`, `update_project(db_id, project)`, `delete_project(db_id)`;
- `replace_users(project_id, users)`;
- `merge_users_from(project_id, donor_project) -> MergeSummary`.

`replace_users` заменяет список юзеров проекта в одной транзакции. `merge_users_from`:

- общие настройки проекта копируются из донора;
- юзеры сливаются по имени: совпавший обновляется, новый добавляется;
- удаления нет.

`SettingsRepository`:

- `get_ai_settings() -> AiSettings`;
- `save_ai_settings(settings)`;
- `get_raw(key)`, `set_raw(key, value)`.

### Миграция v2

Схема создаётся идемпотентно. `app_meta.schema_version`:

1. `ALTER TABLE projects ADD COLUMN default_comment` (если колонки нет).
2. Создать `project_users`, `app_settings`.
3. Для каждого проекта без юзеров создать одного юзера:
   - имя = имя проекта;
   - `git_email` = legacy `projects.git_author_email`;
   - `trackers` = legacy `projects.trackers_json`.
4. Если `ai_settings` отсутствует, взять непустой `projects.ai_json` и сохранить как провайдер `custom` с `base_url`/`model`/`api_key`. Если таких нет — значения по умолчанию:
   - provider `opencode_go`;
   - model `deepseek-v4.1-flash`;
   - ключи пустые.
5. Установить `schema_version = 2`.

Старые `users`, `projects.trackers_json`, `projects.ai_json`, `git_author_email` не удаляются. Цепочка `fill_redmine.db → user_list.py → users → projects → project_users` сохраняется.

## Трекеры

`BaseTracker`:

```python
class BaseTracker(ABC):
    kind: str
    label: str
    fields: tuple[TrackerField, ...]
    can_read: bool = True
    can_write: bool = False

    def is_configured(self) -> bool: ...
    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]: ...
    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError
```

`WorklogDTO`:

```python
@dataclass
class WorklogDTO:
    date: str
    hours: float
    description: str = ""
    issue: str = ""
    source: str = ""
```

### RedmineTracker

Поля:

- `api_key` (secret);
- `user_id` (int);
- `activity_id` (int);
- `issue_id` (int).

Чтение: `/time_entries.json` за период по `user_id`, все issue, с пагинацией.
Запись: `POST /time_entries.json` с `time_entry`:

```json
{
  "issue_id": 2682,
  "user_id": 16,
  "spent_on": "2026-10-27",
  "hours": 4.0,
  "activity_id": 9,
  "comments": "development"
}
```

Ошибки по каждой дате возвращаются как `(date, message)`.

### YoutrackTracker

Поля:

- `access_token` (secret);
- `issue_id` (text, readable id, например `PROJ-123`).

Чтение: `/api/workItems` по `author=me`, пагинация, сумма минут по дням.
Запись: `POST /api/issues/{issue_id}/timeTracking/workItems`:

```json
{
  "date": 1793088000000,
  "duration": {"minutes": 240},
  "text": "development"
}
```

`date` — начало дня в миллисекундах. Автор work item — владелец токена.
Ошибки по каждой дате возвращаются как `(date, message)`.

### Реестр

`configured_trackers(user)` возвращает настроенные трекеры юзера.
`trackers_for_project(project)` — объединение по юзерам (для выбора назначения/источника).
Новый трекер:

1. модуль `trackers/<kind>.py`;
2. `@register_tracker`;
3. поля + чтение (+ запись при необходимости);
4. импорт в `trackers/__init__.py`.

GUI и отчёт сами увидят новый трекер.

## TrackingService

### Типы

```python
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

`row_id` — стабильный ключ строки `f"{user_id}:{date}"`; используется Treeview и редактором строки.

### generate_report

Вход:

- `project: ProjectConfig`;
- `selected_user_ids: list[int]`;
- `destination_kind: str`;
- `source: TrackingSource`;
- `source_kind: str` (для `TRACKER`);
- `start`, `end`;
- `ai_settings` (для коммитов).

Алгоритм:

1. Валидировать период, выбранных юзеров, назначение.
2. Для каждого выбранного юзера:
   - построить destination tracker из `user.trackers[destination_kind]`;
   - проверить `is_configured`;
   - прочитать destination worklogs за период;
   - суммировать existing по дням (все issue).
3. Источник:
   - **AUTOFILL**:
     - для каждого дня периода цель = `workday_hours` на буднях, не входящих в `exclude_dates`; иначе 0;
     - `proposed = max(0, target - existing)`;
     - `comment = project.default_comment`.
   - **TRACKER**:
     - построить source tracker из `user.trackers[source_kind]`;
     - проверить, что `source_kind != destination_kind`;
     - прочитать source worklogs;
     - `proposed = source hours` за день (все часы источника);
     - `comment = project.default_comment`;
     - `source_details` = `source_kind` и issue/описание при наличии.
   - **COMMITS**:
     - проверить `project.git_repo_path` и `user.git_email`;
     - прочитать коммиты `GitClient` за период по email юзера;
     - отправить в AI: проект, юзер, период, destination, existing/deficit, коммиты;
     - AI возвращает JSON `{summary, days: [{date, hours, comment, commit_hashes, confidence}]}`;
     - валидировать: дата в периоде, часы 0..дефицит, шаг 0.5, только реальные хеши;
     - `proposed` = часы AI, `comment` = комментарий AI;
     - если коммитов нет — `proposed = 0`, `comment = "нет коммитов"`, ошибка в строке.
4. Строки отчёта создаются для каждого дня периода и юзера, включая нулевые.
   `include = proposed > 0`.
5. Ошибка одного юзера добавляется в `errors` и не мешает остальным.
6. Ошибка AI для одного юзера — `errors` + строки с error; запись таких строк запрещена.

### write_report

Вход: `TrackingReport` (с отредактированными строками).

1. Взять только `include=True`, `proposed_hours > 0`, `error == ""`.
2. Сгруппировать по юзеру.
3. Для каждого юзера:
   - построить destination tracker;
   - собрать `WorklogDTO(date, hours, description=comment, issue=... из конфига)`;
   - вызвать `create_worklogs`.
4. Успешные строки: `status="записано"`, `include=False`.
5. Ошибки: `status="ошибка"`, `error=...`; остальные строки продолжают писаться.
6. Вернуть `TrackingWriteResult`.

### Валидация отчёта

- часы > 0;
- шаг 0.5;
- не больше 24;
- комментарий не пустой (если пуст — `development`);
- нельзя писать строку с `error`;
- нельзя писать строку с `include=False`.

## AI-провайдеры

### Настройки

`AiSettings`:

```python
@dataclass
class AiSettings:
    provider: str = "opencode_go"
    model: str = "deepseek-v4.1-flash"
    base_url: str = ""
    keys: dict[str, str] = field(default_factory=dict)
```

Провайдеры:

| Провайдер | Base URL | Протокол |
| --- | --- | --- |
| `opencode_go` | `https://opencode.ai/inference/go` | OpenAI Chat / OpenAI Responses / Anthropic Messages |
| `openai` | `https://api.openai.com/v1` | OpenAI Chat Completions |
| `anthropic` | `https://api.anthropic.com/v1` | Anthropic Messages |
| `custom` | из настроек | OpenAI Chat Completions |

### OpenCode Go

- Модели: `GET https://opencode.ai/inference/go/v1/models`, Bearer.
- OpenAI Chat: `POST https://opencode.ai/inference/go/openai/v1/chat/completions`.
- OpenAI Responses: `POST https://opencode.ai/inference/go/openai/v1/responses`; тело `{model, instructions, input}`, ответ разбирается из `output_text`.
- Anthropic Messages: `POST https://opencode.ai/inference/go/anthropic/v1/messages`; заголовки `x-api-key: <key>` и `anthropic-version: 2023-06-01`.
- Заголовки OpenAI-путей: `Authorization: Bearer <key>`, `User-Agent: WorkAssistant/1.0`, `x-opencode-session: <uuid>`.
- Протокол выбирается по модели:
  - Anthropic: `claude-haiku-5-5`, `minimax-m3`, `minimax-m2.7`, `qwen3.8-max`, `qwen3.8-flash`, `qwen3.7-plus`;
  - Responses: `gpt-6-luna`, `gpt-5.6-luna`, `grok-4.7`, `grok-4.6`, `muse-spark-1.3-contributor`, `muse-spark-1.2-contributor`;
  - остальные — OpenAI Chat.
- Если модель неизвестна — пробуем OpenAI Chat, ошибку показываем пользователю.

### OpenAI / Anthropic / Custom

- OpenAI: `GET /models`, `POST /chat/completions`; ключ Bearer.
- Anthropic: `GET /models`, `POST /messages`; заголовки `x-api-key`, `anthropic-version: 2023-06-01`; `max_tokens=4096`.
- Custom: base URL из настроек, `GET /models` (если поддерживается), `POST /chat/completions`; ключ Bearer.

### Клиент AI

Единый интерфейс:

```python
class AiClient(Protocol):
    def complete_json(self, system_prompt: str, user_prompt: str) -> dict: ...
    def list_models(self) -> list[str]: ...
    def check_connection(self) -> None: ...
```

Фабрика `create_ai_client(settings: AiSettings) -> AiClient` выбирает адаптер по провайдеру и модели.
Адаптеры: `OpenAIChatClient`, `OpenAIResponsesClient`, `AnthropicMessagesClient`.
Ошибки приводятся к `AiError` с понятным русским текстом.

### Модели

- Кнопка «Обновить модели» тянет список из API.
- Если запрос не удался — показывается резервный список и текст ошибки.
- Для Custom разрешён ручной ввод модели.
- Выбранная модель сохраняется в `app_settings`.

### Использование

AI вызывается только для `TrackingSource.COMMITS`, по одному запросу на юзера.
Промпт:

- вернуть только JSON;
- использовать только переданные коммиты и хеши;
- не придумывать работу без коммитов;
- часы не больше дефицита, шаг 0.5;
- комментарии по-русски, кратко;
- для дней без коммитов — 0 часов.

## GUI

### Главный экран

```
┌ Work Assistant ─────────────────────────────────────────────┐
│ [Добавить] [Удалить]                         [Настройки AI] │
│ ┌ Проект ──────────────────────────────────────────────────┐│
│ │ ...                                                      ││
│ └──────────────────────────────────────────────────────────┘│
│ Статус: готово                                              │
└─────────────────────────────────────────────────────────────┘
```

- Только список проектов.
- Один клик — выделение для удаления; двойной клик или Enter — открыть.
- «Добавить» — диалог имени проекта; после создания открывается проект.
- «Удалить» — подтверждение, каскадное удаление юзеров.
- «Настройки AI» — глобальное окно.

### Экран проекта

```
┌ Work Assistant — Проект ────────────────────────────────────┐
│ [← Проекты]  Название проекта                              │
│ Меню:                                                     │
│   • Трекинг времени                                        │
└─────────────────────────────────────────────────────────────┘
```

Пока единственный пункт меню. Клик открывает TrackingView.

### Экран трекинга

```
┌ Трекинг времени — Проект ───────────────────────────────────┐
│ [← Проект]                                                  │
│ ┌ Настройки проекта ─────────────────────────── [свернуть] ┐│
│ │ Git-репозиторий [...]  Рабочий день [8]                  ││
│ │ Исключённые даты [...]  Комментарий [development]         ││
│ │ Юзеры: ☑ Имя | email | Redmine | YouTrack                ││
│ │ [Добавить юзера] [Изменить] [Удалить] [Импорт из проекта]││
│ │ [Сохранить настройки]                                    ││
│ └──────────────────────────────────────────────────────────┘│
│ Трекер: [Redmine ▼]  Источник: [Автозаполнение ▼]           │
│ Период: [2026-10-01] — [2026-10-31]  [Сгенерировать отчёт]  │
│ ┌ Отчёт ───────────────────────────────────────────────────┐│
│ │ ☑ | Юзер | Дата | Было | Предложено | Комментарий | ...  ││
│ └──────────────────────────────────────────────────────────┘│
│ [Затрекать]  прогресс/лог                                   │
└─────────────────────────────────────────────────────────────┘
```

- Панель настроек сворачиваемая, отдельная для каждого проекта.
- Чекбоксы юзеров — выбор для текущего отчёта; по умолчанию все включены.
- Изменение настроек/юзеров/периода/трекера/источника сбрасывает отчёт.
- «Сгенерировать отчёт» работает в worker-потоке.
- Treeview отчёта: чекбокс `☑/☐` в первой колонке; Space переключает; двойной клик открывает редактор строки (часы, комментарий, включение).
- «Затрекать» пишет только включённые строки; после записи статусы обновляются.

### Настройки проекта

- Общие поля: git-путь + «Выбрать…», рабочий день, исключённые даты, комментарий по умолчанию.
- Юзеры: таблица с чекбоксами «Трекать», кнопки добавить/изменить/удалить.
- «Импорт из проекта»: выбор донора, подтверждение; общие настройки копируются, юзеры сливаются по имени.
- «Сохранить настройки» — валидация и запись в БД.

### Редактор юзера

- Имя (обязательно);
- git email (для коммитов);
- секции трекеров из `all_trackers()`;
- секретные поля маскируются, есть «показать секреты»;
- пустой трекер = не настроен; частично заполненный = ошибка;
- числовые поля Redmine — int > 0; YouTrack issue — непустая строка.

### Глобальные настройки AI

- Провайдер: OpenCode Go / OpenAI / Anthropic / Custom.
- Модель: combobox + «Обновить модели».
- API key: secret, отдельно для каждого провайдера.
- Base URL: только для Custom.
- «Проверить подключение»: запрос списка моделей или лёгкий chat-запрос.
- «Сохранить».

## Обработка ошибок

- Ошибка одного юзера/дня не отменяет остальные.
- Нет настроенного destination — понятная ошибка до генерации.
- Нет настроенного source — ошибка для конкретного юзера.
- Нет git-пути/email — ошибка для коммитов.
- Нет AI-ключа/модели — ошибка только для источника «из коммитов».
- Ошибка записи — строка с `status="ошибка"` и текстом; успешные строки не откатываются.
- Tkinter: все обновления GUI только через worker-очередь на главном потоке.
- Секреты не логируются.
- Битые JSON-колонки читаются как пустые значения; ошибка пишется в лог.

## Тесты

- Storage:
  - CRUD проектов и юзеров, unique(project_id, name);
  - merge импорт юзеров;
  - `app_settings` round-trip;
  - миграция v2: legacy project → user; legacy AI → global; идемпотентность.
- Trackers:
  - Redmine чтение/запись (mock HTTP), ошибки по датам;
  - YouTrack чтение/запись, duration minutes, issue id, ошибки;
  - реестр и динамические поля.
- TrackingService:
  - autofill: будни, исключённые даты, existing hours, дефицит;
  - from tracker: копирование всех часов, source != destination;
  - commits: коммиты по email, AI-план, валидация, несколько юзеров;
  - отчёт: строки по дням, include/error, редактирование;
  - запись: только включённые, группировка по юзерам, ошибки по строкам.
- AI:
  - OpenAI chat, Anthropic messages, OpenCode Go routing по протоколам;
  - загрузка моделей, fallback;
  - ключи по провайдерам, маскирование;
  - ошибки сети/HTTP/JSON.
- GUI:
  - валидация периода, юзера, отчёта;
  - worker-события и отсутствие Tk-вызовов из фонового потока;
  - ручной smoke: главный экран → проект → трекинг → отчёт → запись.

## Вне объёма

- CLI.
- Автоматический трекинг по расписанию.
- GitHub/GitLab API вместо локального git.
- Шифрование секретов.
- Чат с ИИ внутри приложения.
- Синхронизация между машинами.

## Удаляемое/переиспользуемое

Удаляем:

- `work_assistant_cli.py`, `fill_redmine.py` и CLI-тесты;
- старые вкладки импорта (`gui/import_view.py`), `gui/commit_plan_view.py`;
- старые `imports/manual_import.py`, `imports/youtrack_import.py`, `imports/import_factory.py`, `imports/base_importer.py`;
- `services/import_service.py`, `services/preview_service.py`, `services/issue_service.py`, старые preview-DTO.

Оставляем/переиспользуем:

- `clients/redmine_client.py`, `clients/youtrack_client.py` (расширяем записью);
- `clients/git_client.py`;
- `trackers/` (расширяем записью);
- `storage/migration.py` (legacy user_list);
- `gui/worker.py`, `gui/formatting.py`, `gui/validation.py`;
- `work_assistant.py`, `fill_redmine_gui.py`.
