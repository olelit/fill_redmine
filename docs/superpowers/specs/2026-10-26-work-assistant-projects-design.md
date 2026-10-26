# Дизайн: Work Assistant — проекты, трекеры и план по коммитам

Дата: 2026-10-26
Статус: утверждён

## Цель

Переименовать Fill Redmine в Work Assistant и перейти от плоского списка юзеров к
проектам. Проект — один рабочий контекст: Redmine-аккаунт, YouTrack-токен, локальный
git-репозиторий и настройки ИИ.

Внутри проекта доступны:

1. заполнение Redmine по старой manual-логике;
2. перенос часов из YouTrack в Redmine по старой логике;
3. просмотр своих коммитов за период по всем веткам локального репозитория и
   генерация ИИ-предложения по недостающим до 8 часов дням.

Проекты сохраняются между сессиями в SQLite. В YouTrack ничего не записывается:
ИИ только предлагает план, который можно скопировать.

## Ключевые решения

| Вопрос | Решение |
| --- | --- |
| Модель | Проект = один рабочий контекст (один Redmine-аккаунт, один git-репозиторий) |
| Хранение проектов | SQLite, таблица `projects`, конфиги трекеров и ИИ — JSON-колонки |
| Расширение трекеров | Реестр классов + описание полей; новый трекер без миграции БД |
| Коммиты | Локальный git через CLI, `git log --all`, фильтр по email автора |
| Учёт затреканных часов | Чекбоксы настроенных трекеров на вкладке плана |
| ИИ | OpenAI-совместимый HTTP API, настройки проекта + env fallback |
| Запись в YouTrack | Вне объёма: только предложение и копирование текста |
| Переименование | Внутри репозитория; корневая папка остаётся `fill_redmine` |
| Старые данные | Юзеры один раз мигрируют в проекты; таблица `users` сохраняется |

## Архитектура

```
configs/
  project_config.py        # ProjectConfig
  user_config.py           # остаётся для чтения legacy-таблицы
storage/
  database.py              # схема projects + app_meta, путь к БД
  project_repository.py    # CRUD проектов
  user_repository.py       # legacy-юзеры, нужен для миграции
  migration.py             # user_list.py -> users -> projects, перенос файла БД
trackers/
  base.py                  # BaseTracker, TrackerField, WorklogDTO
  redmine.py               # RedmineTracker
  youtrack.py              # YoutrackTracker
  registry.py              # регистрация и построение трекеров
dto/
  worklog_dto.py
  git_commit_dto.py
  commit_plan_dto.py
clients/
  redmine_client.py        # + чтение time entries за период
  youtrack_client.py       # + пагинация work items
  ai_client.py             # OpenAI-совместимый chat/completions
  git_client.py            # git log через subprocess
services/
  import_service.py        # подготовка и запуск импорта одного проекта
  preview_service.py       # превью записей проекта
  issue_service.py         # без изменений
  commit_plan_service.py   # дефицит часов + запрос к ИИ + валидация плана
gui/
  app.py                   # главное окно и навигация
  project_list_view.py     # список проектов + кнопка «+»
  project_view.py          # экран проекта с вкладками
  project_editor.py        # настройки проекта
  import_view.py           # переиспользуемая панель превью/импорта
  commit_plan_view.py      # коммиты, чекбоксы трекеров, план
  worker.py                # фоновые задачи
  validation.py            # валидация форм
  formatting.py            # форматирование дат/часов
work_assistant.py          # точка входа GUI
work_assistant_cli.py      # CLI по проектам
fill_redmine_gui.py        # legacy-обёртка
fill_redmine.py            # legacy-обёртка CLI
```

Правила зависимостей:

- `gui → services → trackers/clients/storage`; GUI не обращается к SQLite напрямую;
- трекеры не знают про GUI и про то, для чего считаются часы;
- сервисы получают `ProjectConfig` и возвращают DTO;
- новый трекер не требует изменений в `gui/` и `storage/`.

## Модель данных

```sql
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
```

`ProjectConfig`:

```python
@dataclass
class ProjectConfig:
    name: str
    git_repo_path: str = ""
    git_author_email: str = ""
    workday_hours: float = 8.0
    exclude_dates: list[str] = field(default_factory=list)
    trackers: dict[str, dict] = field(default_factory=dict)
    ai: dict[str, object] = field(default_factory=dict)
    db_id: int | None = None
```

`trackers_json`:

```json
{
  "redmine": {
    "api_key": "...",
    "user_id": 16,
    "activity_id": 9,
    "issue_id": 2682,
    "comment": "development"
  },
  "youtrack": {"access_token": "..."}
}
```

`ai_json`:

```json
{
  "base_url": "https://api.openai.com/v1",
  "model": "gpt-4o-mini",
  "api_key": "..."
}
```

Пустые настройки трекера означают, что трекер не настроен. Обязательные поля
проверяются при использовании, а не при сохранении: можно сохранить проект и
дозаполнить позже. Если заполнена только часть полей трекера, валидация формы
показывает ошибку.

Секреты хранятся в SQLite в открытом виде, как раньше в `user_list.py`. Файл БД
имеет права `600`. В UI секретные поля маскируются и есть переключатель «показать».

### Путь к БД и миграция

- `WORK_ASSISTANT_DB` — новый env; если не задан, используется `FILL_REDMINE_DB`;
  иначе `<корень>/work_assistant.db`.
- Если `work_assistant.db` не существует, а `fill_redmine.db` существует, старый
  файл переименовывается в новый при старте (при ошибке — копирование). В лог
  пишется сообщение о переносе.
- Схема создаётся идемпотентно.
- `user_list.py` сначала мигрирует в `users` старым механизмом, затем
  `migrate_users_to_projects()` конвертирует юзеров в проекты.
- Миграция юзеров в проекты выполняется один раз и отмечается ключом
  `legacy_users_migrated=1` в `app_meta`. Если проектов ещё нет, а юзеры есть —
  каждый юзер становится проектом. Имя сохраняется; при конфликте уникальности
  добавляется суффикс ` (2)`, ` (3)` и т.д.
- Redmine-поля юзера переносятся в `trackers.redmine`; непустой YouTrack-токен —
  в `trackers.youtrack`; `exclude_dates` и имя — в проект.

## Трекеры

`trackers/base.py`:

```python
@dataclass(frozen=True)
class TrackerField:
    key: str
    label: str
    kind: str = "text"          # text | int | secret | textarea
    required: bool = True
    placeholder: str = ""


@dataclass
class WorklogDTO:
    date: str
    hours: float
    description: str = ""
    issue: str = ""
    source: str = ""


class BaseTracker(ABC):
    kind: str
    label: str
    fields: tuple[TrackerField, ...]
    can_read: bool = True
    can_write: bool = False

    def __init__(self, config: dict): ...
    def is_configured(self) -> bool: ...
    @abstractmethod
    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]: ...
    def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
        raise NotImplementedError
```

`create_worklogs` — точка расширения для будущих трекеров с записью часов;
сейчас её реализует только Redmine.

`RedmineTracker`:

- поля: `api_key` (secret), `user_id` (int), `activity_id` (int), `issue_id` (int),
  `comment` (textarea);
- `get_worklogs()` читает `/time_entries.json` за период по `user_id` (все issue),
  с пагинацией, и возвращает `WorklogDTO`;
- `can_write=True`; методы записи часов используются старой manual-логикой.

`YoutrackTracker`:

- поле `access_token` (secret);
- `get_worklogs()` читает work items за период по `author=me`, с пагинацией,
  суммирует минуты по дням;
- `can_write=False` (запись в YouTrack вне объёма).

`trackers/registry.py`:

- `register_tracker(cls)`, `all_trackers()`, `get_tracker_class(kind)`;
- `configured_trackers(project) -> list[BaseTracker]`;
- `tracker_field_errors(project) -> list[str]` для валидации настроек.

Добавление нового трекера:

1. создать `trackers/<kind>.py` с классом-наследником `BaseTracker`;
2. добавить импорт и регистрацию в `trackers/__init__.py`;
3. при необходимости реализовать `get_worklogs()` и `can_write`.

GUI автоматически покажет поля из `fields` в настройках проекта и чекбокс на
вкладке плана. Миграции и правки окон не нужны.

## Сервисы импорта

Старая логика сохраняется:

- **Redmine**: на каждый будний день текущего месяца, которого нет в
  `exclude_dates` и по которому ещё нет time entry, создаётся 8 часов.
- **YouTrack → Redmine**: work items текущего месяца суммируются по дням и
  создаются как time entries в Redmine.

`ImportService` работает с одним проектом:

```python
class ImportAction(StrEnum):
    REDMINE_FILL = "redmine_fill"
    YOUTRACK_TRANSFER = "youtrack_transfer"

def prepare(project: ProjectConfig, action: ImportAction) -> PrepareResult: ...
async def run(items: list[PreparedImport], progress_cb=None) -> ImportSummary: ...
```

`PrepareResult` содержит `items` (записи + превью) и `errors` (`PreviewDTO`).
`PreviewDTO` переименовывается семантически: `project_name`, `action`, `issue_id`,
`issue_subject`, `issue_url`, `ranges`, `total_hours`, `error`. Для совместимости
CLI печать превью сохраняется.

Ошибки одного действия не роняют приложение: они попадают в лог и в превью с
полем `error`.

## Git

`clients/git_client.py`:

```python
@dataclass
class GitCommitDTO:
    hash: str
    author_name: str
    author_email: str
    date: str          # ISO 8601 с часовым поясом
    subject: str
    body: str


class GitClient:
    def __init__(self, repo_path: str): ...
    def validate(self) -> None: ...
    def list_commits(self, email: str, start: date, end: date) -> list[GitCommitDTO]: ...
```

Реализация:

- проверка, что путь существует и является git-репозиторием
  (`git rev-parse --is-inside-work-tree`);
- `git log --all --author=<email> --since=<start>T00:00:00 --until=<end>T23:59:59`
  с форматом, разделённым `\x1f`/`\x1e`;
- `--all` покрывает локальные и удалённые ветки; дубликаты по хешу убираются;
- сортировка по дате убыванию;
- пустой email или отсутствие коммитов — понятная ошибка/пустой список.

## Расчёт дефицита и ИИ

`services/commit_plan_service.py`:

1. Принимает проект, период, список выбранных kind трекеров и коммиты.
2. Для каждого выбранного трекера вызывает `get_worklogs(start, end)`.
   Если трекер не настроен или упал — генерация прерывается с сообщением,
   чтобы не считать дефицит по неполным данным.
3. Суммирует часы по дням. Часы разных трекеров складываются (пользователь сам
   отвечает за отсутствие дублей, поэтому и нужны чекбоксы).
4. Для каждого дня периода:
   - будни, не входящие в `exclude_dates`, имеют цель `workday_hours`;
   - выходные и исключённые дни имеют цель 0;
   - `deficit = max(0, target - existing)`.
5. Формирует компактный JSON: проект, период, цель, дни с коммитами и дефицитом.
6. Отправляет запрос в `AiClient`.
7. Валидирует ответ:
   - дата входит в период;
   - часы `0 <= hours <= deficit`;
   - шаг 0.5 часа;
   - `commit_hashes` — только хеши из переданного набора;
   - невалидные дни отбрасываются с предупреждением в лог.

Ответ ИИ (строгий JSON):

```json
{
  "summary": "краткий итог",
  "days": [
    {
      "date": "2026-10-26",
      "hours": 4.0,
      "comment": "Реализация импорта проектов",
      "commit_hashes": ["abc1234"],
      "confidence": "high"
    }
  ]
}
```

`AiClient`:

- `POST {base_url}/chat/completions`;
- заголовок `Authorization: Bearer <api_key>`;
- тело: `model`, `messages`, `temperature=0.2`;
- таймаут 120 секунд;
- ответ парсится как JSON; допускается снятие markdown-обёртки ```json ... ```;
- ошибки: нет конфига, HTTP-ошибка, пустой/невалидный JSON — понятное исключение
  с текстом ответа (обрезанным) для диагностики.

Конфиг ИИ: поля проекта перекрывают env `OPENAI_BASE_URL`, `OPENAI_API_KEY`,
`OPENAI_MODEL`. Если base_url не задан, используется `https://api.openai.com/v1`.
Модель и ключ обязательны для генерации.

Промпт требует:

- не выдумывать коммиты и хеши;
- писать комментарии по-русски, кратко и по делу;
- предлагать часы только на дни с дефицитом;
- если коммитов за день нет, не придумывать работу, а вернуть 0 часов и
  пояснение в комментарии;
- не превышать дефицит.

## GUI

Одно окно, навигация «список проектов ↔ проект».

### Главный экран

```
┌ Work Assistant ─────────────────────────────────────────────┐
│ [＋] [Открыть] [Настройки] [Удалить]                        │
│ ┌ Имя │ Git-репозиторий │ Трекеры ────────────────────────┐ │
│ │ ...                                                     │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Статус: готово                                              │
└─────────────────────────────────────────────────────────────┘
```

- `+` открывает `ProjectEditor` с пустым проектом.
- Двойной клик или «Открыть» переключает на экран проекта.
- «Настройки» — редактор выбранного проекта.
- «Удалить» — подтверждение.
- После добавления/изменения список обновляется.
- Пустой список показывает подсказку «Нажмите +, чтобы добавить проект».

### Экран проекта

```
┌ Work Assistant — Проект ────────────────────────────────────┐
│ [← Проекты]  Название проекта              [Настройки]      │
│ ┌ Redmine │ YouTrack → Redmine │ Коммиты и план ───────────┐│
│ │ ...                                                      ││
│ └──────────────────────────────────────────────────────────┘│
│ Статус: готово                                              │
└─────────────────────────────────────────────────────────────┘
```

**Вкладка Redmine** и **вкладка YouTrack → Redmine** используют один
переиспользуемый `ImportView` с разными `action` и заголовками:

- «Построить превью»;
- «Запустить импорт»;
- таблица: issue, тема, периоды, всего;
- прогресс-бар и лог;
- кнопки блокируются на время работы;
- ошибки в лог и диалог.

Вкладки создаются лениво при первом открытии проекта. Каждая панель использует
уникальный префикс событий worker'а, чтобы не перехватывать события другой панели.

**Вкладка «Коммиты и план»**:

- поля периода `с`/`по` в формате `ГГГГ-ММ-ДД`, по умолчанию первый день
  текущего месяца — сегодня;
- кнопка «Загрузить коммиты»;
- таблица коммитов: дата, хеш (7 символов), тема;
- блок «Учитывать уже затреканные часы»: чекбоксы для каждого настроенного
  трекера; по умолчанию выбран YouTrack, если настроен, иначе Redmine;
- выбор сохраняется в `ai_json["selected_trackers"]`;
- кнопка «Сгенерировать план» (disabled, если нет коммитов, не выбран трекер
  или не настроен ИИ);
- результат: таблица «дата, было, дефицит, предложено, комментарий, коммиты»,
  итоговый текст и кнопка «Копировать план»;
- отдельная надпись: «В YouTrack ничего не записывается — план нужно вставить
  вручную».

Ошибки загрузки коммитов/ИИ показываются в логе вкладки и в `messagebox`.

### Настройки проекта

Диалог с тремя секциями (можно `ttk.Notebook`):

1. **Общее**:
   - имя (обязательно, уникальное);
   - git-путь + кнопка «Выбрать…»;
   - email автора + кнопка «Из git» (читает `git config user.email`);
   - рабочий день, часов (0 < x <= 24, по умолчанию 8);
   - исключённые даты (список + добавить/удалить, формат `ГГГГ-ММ-ДД`).
2. **Трекеры**:
   - для каждого зарегистрированного трекера — секция с полями из `fields`;
   - секретные поля маскируются, есть общий переключатель «показать секреты»;
   - пустые поля = трекер не настроен;
   - частично заполненный трекер = ошибка валидации.
3. **ИИ**:
   - base_url;
   - model;
   - api_key (secret).
   - подсказка про env fallback.

Кнопки «Сохранить»/«Отмена», инлайн-ошибки.

### Навигация и занятость

- Пока идёт импорт или генерация, переход назад/закрытие окна спрашивает
  подтверждение.
- Worker остаётся один на приложение; события маршрутизируются по префиксам.
- Статус-бар общий.

## Переименование и совместимость

- `fill_redmine_gui.py` → `work_assistant.py` (GUI);
- `fill_redmine.py` → `work_assistant_cli.py` (CLI);
- `fill_redmine_gui.py` и `fill_redmine.py` остаются тонкими обёртками, которые
  вызывают новый entry point, чтобы не сломать существующие ярлыки. Для CLI при
  запуске через старую обёртку в stderr печатается предупреждение о переименовании.
- заголовок окна и все пользовательские строки — Work Assistant;
- `README.md` переписывается под новое название и проекты;
- `Fill Redmine.desktop` → `Work Assistant.desktop`;
- `run_gui.sh` запускает `work_assistant.py`;
- `scripts/install_desktop.sh` ставит новый ярлык и, если возможно, удаляет
  старый `fill-redmine-gui.desktop`;
- `assets/fill_redmine.svg` → `assets/work_assistant.svg`;
- `.gitignore`: `work_assistant.db`, `fill_redmine.db` (legacy);
- `work_assistant_cli.py`:
  - без аргументов печатает список проектов;
  - `--project ID` и `--action {redmine_fill,youtrack_transfer}` запускают
    импорт с подтверждением, как старая CLI;
  - `--id` сохраняется как override Redmine issue для выбранного проекта.

## Обработка ошибок

- Сетевые/API-ошибки — в лог и `messagebox`, приложение продолжает работу.
- Ошибка одного трекера при расчёте дефицита — генерация прерывается с
  указанием трекера; пользователь может снять галочку и повторить.
- Ошибка git — «не git-репозиторий», «не задан email», «нет коммитов».
- Ошибка ИИ — нет ключа/модели, HTTP-статус, невалидный JSON; показывается
  обрезанный ответ.
- Битые JSON-колонки в БД читаются как пустые значения с предупреждением, без
  падения приложения.
- Удаление проекта не удаляет старых юзеров и не трогает Redmine/YouTrack.

## Тесты

Обновить существующие тесты под `ProjectConfig`/проекты. Добавить:

- `ProjectRepository`: CRUD, JSON round-trip, уникальность имени;
- миграция `users → projects`: поля, токен, даты, идемпотентность, суффиксы
  при конфликте имён;
- перенос файла БД `fill_redmine.db → work_assistant.db` (tmp_path);
- реестр трекеров: регистрация, `configured_trackers`, валидация полей;
- `RedmineTracker` и `YoutrackTracker` с моками HTTP;
- `GitClient` на временном git-репозитории: все ветки, фильтр по email,
  период, дубликаты;
- `AiClient`: успешный ответ, markdown-обёртка, HTTP-ошибка, мусорный JSON;
- `CommitPlanService`: дефицит по будням, исключённые даты, выходные,
  сложение трекеров, обрезка часов, отбрасывание выдуманных хешей;
- валидация формы проекта (имя, числа, даты, частично заполненный трекер);
- существующие тесты импорта/превью/worker/форматирования — зелёные.

Ручная проверка:

- запуск GUI, добавление/редактирование/удаление проекта;
- перезапуск приложения — проекты на месте;
- оба импорта на тестовом проекте;
- загрузка коммитов и генерация плана с реальным/замоканным ИИ;
- кнопка «Копировать план».

## Вне объёма

- Автоматическая запись предложенного плана в YouTrack.
- Шифрование секретов.
- GitHub/GitLab API вместо локального git.
- Синхронизация проектов между машинами.
- Автозапуск GUI.
- Переименование корневой папки репозитория.
