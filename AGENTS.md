# AGENTS.md

This file provides guidance for agents working on this codebase.

## Project Overview

Work Assistant is a Python/Tkinter GUI for tracking time across projects. It
reads worklogs from tracker sources (Redmine, YouTrack, git commits), builds a
tracking report (optionally with AI help) and writes the approved hours to a
destination tracker. It uses:

- `tkinter` for the GUI
- `requests` for sync HTTP requests
- `python-dotenv` for environment variable management

There is no CLI entry point: the application is launched from `work_assistant.py`
(and `fill_redmine_gui.py` is kept as an alias).

## Project Structure

```
fill_redmine/
├── work_assistant.py        # Entry point: migrations + MainWindow
├── fill_redmine_gui.py      # Alias entry point
├── gui/                     # Tkinter views, dialogs and validation
│   ├── app.py               # MainWindow navigation
│   ├── project_list_view.py
│   ├── project_view.py
│   ├── project_settings_panel.py
│   ├── user_editor.py
│   ├── tracking_view.py
│   ├── report_editor.py
│   ├── ai_settings_dialog.py
│   ├── worker.py            # Background worker for Tk callbacks
│   └── validation.py        # Shared form validation helpers
├── services/                # Use cases
│   ├── tracking_service.py
│   └── tracking_plan_service.py
├── trackers/                # Tracker plugins
│   ├── base.py              # BaseTracker / TrackerField
│   ├── registry.py          # register_tracker / all_trackers
│   ├── redmine.py
│   └── youtrack.py
├── clients/                 # HTTP clients
│   ├── redmine_client.py
│   ├── youtrack_client.py
│   ├── git_client.py
│   └── ai/                  # Multi-provider AI clients
├── dto/                     # Data transfer objects (dataclasses)
├── storage/                 # SQLite repositories and migrations
└── configs/                 # Dataclasses and env config
```

## Build/Run Commands

### Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables (copy .env.example to .env and fill in values)
cp .env.example .env

# Run the application
python work_assistant.py
```

The GUI requires a display; there are no CLI commands.

### Testing

Tests live in `tests/` and use `pytest`:

```bash
# Install test dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run a single test file
pytest tests/test_tracking_service.py

# Run a single test function
pytest tests/test_tracking_service.py::test_build_report

# Run tests matching a pattern
pytest -k "tracking"
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

from dotenv import load_dotenv

from configs.config import Config
from dto.worklog_dto import WorklogDTO
```

### Type Annotations

- Always use type hints for function parameters and return types
- Use built-in types (`list`, `dict`) or types from `typing` module
- Use `|` syntax for unions (Python 3.10+)

```python
def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
    ...

def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
    ...
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `BaseTracker`, `Config`)
- **Functions/Variables**: snake_case (e.g., `get_worklogs`, `redmine_url`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MANUAL = 'manual'`)
- **Private methods**: Prefix with underscore (e.g., `_private_method`)

### Dataclasses for DTOs

Use `@dataclass` decorator for simple data containers:

```python
from dataclasses import dataclass

@dataclass
class WorklogDTO:
    date: str
    hours: float
    description: str = ""
```

### Error Handling

- Use try/except for operations that can fail (e.g., network calls, parsing)
- Use specific exception types when possible
- Call `response.raise_for_status()` for HTTP responses, or collect errors per
  record and return them to the caller

```python
# Good: specific exception handling
try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
except requests.RequestException as exc:
    return [(date, str(exc))]

# Good: HTTP error checking
response.raise_for_status()
```

### User-Facing Strings

- GUI labels, messages and validation errors are in Russian
- Technical identifiers (field keys, tracker kinds, env vars) stay in English

### Formatting

- Use f-strings for string formatting (not % or .format())
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters (recommended)
- Add blank lines between class definitions and major sections

### Tracker Plugins

- New trackers subclass `BaseTracker` in `trackers/`
- Register them with `@register_tracker` and import the module in
  `trackers/__init__.py`
- `fields` drives the settings form; `get_worklogs` is the read path;
  `create_worklogs` is optional (`can_write = True`)

## Environment Variables

- Never commit secrets to version control
- Use `.env` files for local development (already in `.gitignore`)
- Document required variables in `.env.example`

Required variables:
- `REDMINE_BASE_URL` — Redmine instance URL
- `YOUTRACK_BASE_URL` — YouTrack instance URL
- `WORK_ASSISTANT_DB` — optional path to the SQLite database
  (`FILL_REDMINE_DB` is still accepted as a legacy alias)

Tracker keys, AI provider keys and models are stored in SQLite, not in env.

## Making Changes

1. Run the GUI (`python work_assistant.py`) and test the flow manually
2. Run `pytest` to verify the suite is green
3. If adding ruff, run `ruff check . && ruff format .` before committing
4. Each task ends with green tests and its own commit
