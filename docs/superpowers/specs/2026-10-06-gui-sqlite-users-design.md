# Дизайн: GUI для Fill Redmine + хранение юзеров в SQLite

Дата: 2026-10-06
Статус: утверждён

## Цель

Дать проекту полноценный десктопный GUI вместо редактирования `user_list.py`:

- управление юзерами (добавление/редактирование/удаление, вкл/выкл);
- хранение юзеров в SQLite как единый источник правды для GUI и CLI;
- предпросмотр записей, запуск импорта с прогрессом и логом в окне;
- ярлык в меню приложений KDE с автоматическим закреплением на панели.

## Ключевые решения

| Вопрос | Решение |
| --- | --- |
| Технология GUI | Tkinter (ttk) |
| Хранение | SQLite, единственный источник правды; CLI тоже читает БД |
| Файл БД | `fill_redmine.db` в корне проекта, `chmod 600`, переопределяется `FILL_REDMINE_DB` |
| Первичная миграция | Из `user_list.py` при пустой БД, файл переименовывается в `user_list.py.migrated` |
| Архитектура | Слоистый рефакторинг: `gui → services → storage/clients` |
| Язык интерфейса | Смешанный: русские подписи, технические термины — как в коде |
| Ярлык | `~/.local/share/applications/fill-redmine-gui.desktop` + автопин в Plasma 6 через D-Bus |

## Архитектура

```
storage/
  database.py          # соединение, PRAGMA, create_schema()
  user_repository.py   # CRUD над таблицей users, row -> UserConfig
  migration.py         # первичный перенос USERS из user_list.py в БД
services/
  import_service.py    # вынесено из fill_redmine.py: build_preview() + run_import(progress_cb, log_cb)
  preview_service.py   # + build_user_preview() -> PreviewDTO; print_* остаются для CLI
gui/
  app.py               # главное окно: список юзеров + панель импорта
  user_editor.py       # диалог добавления/редактирования юзера
  import_view.py       # таблица превью, прогресс-бар, лог
  worker.py            # фоновый поток + queue + root.after (потокобезопасность Tkinter)
fill_redmine_gui.py    # точка входа GUI
run_gui.sh             # активация venv + запуск (для .desktop)
assets/fill_redmine.svg
scripts/install_desktop.sh
```

Правила зависимостей:

- `gui → services → storage/clients`; GUI не обращается к sqlite напрямую;
- `fill_redmine.py` сохраняет CLI-интерфейс (`--id`), но читает юзеров из репозитория;
- `UserConfig` получает поле `db_id: int | None = None` для адресации при edit/delete;
- импорт принимает `on_progress(completed, total)`; CLI передаёт старый print-прогресс, GUI — колбэк в очередь.

## Модель данных

```sql
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
    exclude_dates TEXT NOT NULL DEFAULT '[]'   -- JSON-массив дат
);
```

Репозиторий: `list_users()`, `get_user(db_id)`, `add_user(UserConfig)`, `update_user(UserConfig)`,
`delete_user(db_id)`, `set_enabled(db_id, bool)`.

`PreviewDTO` (для GUI-таблицы): `user_name`, `driver`, `issue_id`, `issue_subject`, `issue_url`,
`ranges: list[DateRangeDTO]` (`start_date`, `end_date`, `hours`), `total_hours`, `error: str | None`.

Миграция: при старте, если таблица пуста и `user_list.py` существует — переносит `USERS`
и переименовывает файл в `user_list.py.migrated`. Если файла нет — БД остаётся пустой.
Ошибки импорта не роняют приложение: warning в лог. `fill_redmine.db` и `user_list.py.migrated`
добавляются в `.gitignore`.

Секреты лежат в SQLite в открытом виде (как раньше в `user_list.py`); в UI поля с ключами
маскируются (`show="*"`, кнопка «показать»).

## GUI

```
┌ Fill Redmine ───────────────────────────────────────────────────┐
│ [Добавить] [Изменить] [Удалить]                                 │
│ ┌ Вкл │ Имя │ Driver │ Issue │ user_id │ activity_id │ ... ────┐│
│ │  ☑  │Олег │youtrack│ 2682  │   16    │      9      │         ││
│ └─────────────────────────────────────────────────────────────┘│
│ ┌ Превью и импорт ─────────────────────────────────────────────┐│
│ │ [Построить превью]  [Запустить импорт]    ☑ только включённые││
│ │ ┌ Имя │ Issue │ Тема │ Периоды/часы │ Всего ───────────────┐ ││
│ │ ├──────────────────────────────────────────────────────────┤ ││
│ │ │ прогресс-бар   «Олег 5/20»                               │ ││
│ │ │ лог (read-only, скролл)                                  │ ││
│ │ └──────────────────────────────────────────────────────────┘ ││
│ └──────────────────────────────────────────────────────────────┘│
│ Статус: готово                                                  │
└─────────────────────────────────────────────────────────────────┘
```

- **Диалог юзера**: все поля `UserConfig`; driver — radio manual/youtrack
  (токен активен только для youtrack); `exclude_dates` — ввод даты + «Добавить»/«Удалить»
  (в БД JSON); ключи маскируются. Валидация инлайн: обязательное имя, целые
  `issue_id/user_id/activity_id > 0`.
- **Превью**: worker-поток → `ImportService.build_preview()` (список `PreviewDTO`) → таблица
  со свёрнутыми диапазонами дат («01.10–04.10 — 8h») и итогом; issue-инфо в шапке строки
  юзера. Ошибка одного юзера — в лог и поле `error`, остальные продолжают.
- **Импорт**: диалог подтверждения → worker-поток → прогресс-бар и лог; кнопки блокируются,
  закрытие окна во время импорта предупреждает. По завершении — итог (успешно/ошибок).
- **Ошибки**: сете/API — в лог; падение в worker ловится и показывается, приложение не падает.
- Импортируются только включённые юзеры (или выделенные, если снята галка).

## Ярлык и автопин

- `scripts/install_desktop.sh`:
  - создаёт `assets/fill_redmine.svg` и `run_gui.sh` (venv + `python fill_redmine_gui.py`);
  - пишет `~/.local/share/applications/fill-redmine-gui.desktop`
    (`Terminal=false`, `WorkingDirectory=корень проекта`, `Icon=assets/fill_redmine.svg`);
  - обновляет кэш меню (`update-desktop-database`);
  - автопин Plasma 6 через
    `qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript`:
    скрипт ищет Task Manager / Icons-only Task Manager на панели и добавляет launcher;
  - при неудаче автопина печатает инструкцию «ПКМ → Закрепить на панели».
- Проверка зависимости `tk`: установщик проверяет `import tkinter`, при отсутствии подсказывает
  `sudo pacman -S tk` (нужен sudo).

## Зависимости и тесты

- Системная зависимость: `tk` (Arch/CachyOS). Dev-зависимость: `pytest` (`requirements-dev.txt`).
- Тесты (pytest, временная БД):
  - CRUD репозитория;
  - миграция из `user_list.py` (и отсутствие миграции при непустой БД);
  - `build_user_preview` (диапазоны дат, итоги);
  - `ImportService` с моками клиентов + проверка вызова `on_progress`;
  - CLI на репозитории.
- Ручная проверка: запуск GUI, `python fill_redmine.py --help`, ярлык.

## Вне объёма

- Шифрование секретов.
- Автозапуск GUI при входе в систему.
- Экспорт обратно в `user_list.py`.
- GUI-тесты.
