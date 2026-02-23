# Fill Redmine

Импорт временных записей из YouTrack в Redmine.

## Установка

### 1. Создание виртуального окружения

```bash
python3 -m venv venv
```

### 2. Активация виртуального окружения

```bash
# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

## Настройка

### Создание файла user_list.py

В корне проекта создайте файл `user_list.py` со списком пользователей:

```python
from configs.user_config import UserConfig


USERS = [
    UserConfig(
        is_enable=True,
        name="Ваше_имя",
        redmine_api_key="ваш_api_ключ_redmine",
        user_id=ваш_user_id,
        activity_id=id_активности,
        comment="комментарий",
        issue_id=id_задачи,
        driver="manual",  # или "youtrack"
        youtrack_access_token="токен_youtrack",
        exclude_dates=[],
    ),
]
```

Пример можно посмотреть в файле `user_list.py.example` (если есть).

## Запуск

```bash
python fill_redmine.py
```

## Структура проекта

- `fill_redmine.py` — главный файл
- `configs/user_config.py` — класс конфигурации пользователя
- `user_list.py` — список пользователей (не коммитится в git)
- `imports/` — импортеры для разных источников
- `dto/` — объекты передачи данных
