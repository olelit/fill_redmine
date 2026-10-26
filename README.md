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

Путь к базе данных переопределяется переменной окружения `WORK_ASSISTANT_DB`
(legacy-переменная `FILL_REDMINE_DB` тоже поддерживается).

## Ярлык на панели KDE

```bash
bash scripts/install_desktop.sh
```

Скрипт ставит ярлык в меню приложений и пытается закрепить его на панели Plasma 6.
Если автопин не удался — закрепите вручную: ПКМ по иконке → «Закрепить на панели».

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
