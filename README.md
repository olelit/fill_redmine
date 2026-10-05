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
