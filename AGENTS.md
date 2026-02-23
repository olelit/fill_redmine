# AGENTS.md

This file provides guidance for agents working on this codebase.

## Project Overview

This is a Python async project that imports time entries from YouTrack to Redmine. It uses:
- `aiohttp` for async HTTP requests
- `requests` for sync HTTP requests
- `python-dotenv` for environment variable management

## Project Structure

```
fill_redmine/
├── fill_redmine.py       # Main entry point
├── configs/              # Configuration classes
│   ├── config.py
│   └── iterable_config_dto.py
├── dto/                  # Data Transfer Objects (dataclasses)
│   └── date_hours_dto.py
└── imports/              # Source importers
    ├── base_importer.py   # Abstract base class
    ├── import_factory.py  # Factory for creating importers
    ├── manual_import.py   # Manual time entry importer
    └── youtrack_import.py # YouTrack importer
```

## Build/Run Commands

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables (copy .env.example to .env and fill in values)
cp .env.example .env

# Run the application
python fill_redmine.py
```

### Testing

This project currently has no test framework. Recommended setup:

```bash
# Install pytest
pip install pytest pytest-asyncio

# Run all tests
pytest

# Run a single test file
pytest tests/test_manual_import.py

# Run a single test function
pytest tests/test_manual_import.py::test_create_record_list

# Run tests matching a pattern
pytest -k "test_name"
```

### Linting and Formatting

This project currently has no linting configuration. Recommended setup:

```bash
# Install ruff (fast linter/formatter)
pip install ruff

# Run linter
ruff check .

# Run formatter
ruff format .

# Run both
ruff check . && ruff format .
```

## Code Style Guidelines

### Imports

- Use absolute imports (e.g., `from configs.config import Config`)
- Order: stdlib → third-party → local project
- Separate each group with a blank line
- Do NOT use relative imports (e.g., `from . import x`)

```python
# Correct
import os
import asyncio

from dotenv import load_dotenv

from configs.config import Config
from dto.date_hours_dto import DateHoursDTO
```

### Type Annotations

- Always use type hints for function parameters and return types
- Use built-in types (`list`, `dict`) or types from `typing` module
- Use `|` syntax for unions (Python 3.10+) or `Optional[]` for older code

```python
def create_record_list(self) -> list[DateHoursDTO]:
    ...

async def update_redmine_activity(
    self, 
    uid: int, 
    iid: int, 
    comment: str, 
    activity_id: int, 
    api_key: str, 
    records: list[DateHoursDTO]
) -> None:
    ...
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `BaseImporter`, `Config`)
- **Functions/Variables**: snake_case (e.g., `create_record_list`, `redmine_url`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MANUAL = 'manual'`)
- **Private methods**: Prefix with underscore (e.g., `_private_method`)

### Dataclasses for DTOs

Use `@dataclass` decorator for simple data containers:

```python
from dataclasses import dataclass

@dataclass
class DateHoursDTO:
    date: str
    hours: int
```

### Error Handling

- Use try/except for operations that can fail (e.g., network calls, parsing)
- Print errors for user-facing scripts
- Use specific exception types when possible
- Consider using `response.raise_for_status()` for HTTP responses

```python
# Good: Specific exception handling
try:
    root = et.fromstring(response.text)
    for entry in root.findall("time_entry"):
        ...
except et.ParseError as e:
    print(f"XML parse error: {e}")

# Good: HTTP error checking
response.raise_for_status()
```

### Async Code

- Use `async def` for async functions
- Use `await` for async calls
- Use `asyncio.gather()` for concurrent operations

```python
async def run(self):
    records = self.create_record_list()
    async with aiohttp.ClientSession() as session:
        tasks = []
        for record in records:
            tasks.append(self.set_time(session, ...))
        await asyncio.gather(*tasks)
```

### Formatting

- Use f-strings for string formatting (not % or .format())
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters (recommended)
- Add blank lines between class definitions and major sections

### Class Structure

- Use ABC (Abstract Base Class) for interfaces
- Use `@abstractmethod` decorator for methods that subclasses must implement

```python
from abc import ABC, abstractmethod

class BaseImporter(ABC):
    @abstractmethod
    def create_record_list(self) -> list[DateHoursDTO]:
        pass
```

### Constants

Define source types as module-level constants:

```python
MANUAL = 'manual'
YOUTRACK = 'youtrack'
```

## Environment Variables

- Never commit secrets to version control
- Use `.env` files for local development (already in `.gitignore`)
- Document required variables in `.env.example`

Required variables:
- `REDMINE_BASE_URL` - Redmine instance URL
- `YOUTRACK_BASE_URL` - YouTrack instance URL
- `SOURCE_{N}` - Source type (manual/youtrack) for config N
- `REDMINE_API_KEY_{N}` - API key for Redmine
- `USER_ID_{N}` - User ID for time entries
- `ACTIVITY_ID_{N}` - Activity/Time entry category ID
- `ISSUE_ID_{N}` - Target issue ID
- `COMMENT_{N}` - Default comment for entries
- `YOUTRACK_ACCESS_TOKEN_{N}` - YouTrack API token (for youtrack source)
- `EXCLUDE_DATES_{N}` - Comma-separated dates to skip

## Making Changes

1. Test locally with `python fill_redmine.py` after changes
2. If adding tests, run `pytest` to verify
3. If adding ruff, run `ruff check . && ruff format .` before committing
