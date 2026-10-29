# AGENTS.md

This file provides guidance for agents working on this codebase.

## Project Overview

Work Assistant is a Python/Tkinter GUI for tracking time across projects. It
reads worklogs from tracker sources (Redmine, YouTrack, git commits), builds a
tracking report (optionally with AI help) and writes the approved hours to a
destination tracker. A local MCP server exposes the same trackers and git
client to OpenCode for per-issue YouTrack fill. It uses:

- `tkinter` for the GUI
- `requests` for sync HTTP requests
- `python-dotenv` for environment variable management
- `mcp` for the local stdio server

There is no CLI entry point: the application is launched from `work_assistant.py`
(and `fill_redmine_gui.py` is kept as an alias). The MCP server is started with
`python -m mcp_server`.

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
├── configs/                 # Dataclasses and env config
├── mcp_server/              # Local stdio MCP server (OpenCode)
│   ├── __main__.py          # `python -m mcp_server` entry point
│   ├── app.py               # create_server: tool registration
│   ├── config.py            # JSON user profiles (config/users.json)
│   ├── user_tools.py        # list_enabled_users
│   ├── read_tools.py        # get_worklogs, get_git_commits
│   ├── tracker_access.py    # profile -> tracker construction
│   ├── youtrack_tools.py    # prepare_youtrack_fill
│   ├── plans.py             # one-time write plans
│   ├── write_tools.py       # write_plan approval gate
│   └── writer.py            # approved plan execution
└── config/
    ├── users.example.json   # tracked template with blank placeholders
    └── users.json           # ignored, 0600, real tokens
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

The GUI requires a display; there are no GUI CLI commands. The MCP server runs
over stdio instead (see below).

### Running the MCP server

```bash
# One-time profile setup; config/users.json is ignored and must be 0600
cp config/users.example.json config/users.json
chmod 600 config/users.json

# Start the stdio server directly
.venv/bin/python -m mcp_server
```

OpenCode starts it automatically from `.opencode/opencode.json`
(`.venv/bin/python -m mcp_server`, `cwd: "."`, `codemode: false`,
`protocol: "legacy"`). Verify with `opencode mcp list` (expect
`work-assistant connected`).

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

## MCP Server

`mcp_server/` is a local stdio server for OpenCode. It exposes exactly five
tools and no prompts/resources:

- `list_enabled_users` — enabled profile names and tracker kinds only;
- `get_worklogs` — worklogs for one profile and period;
- `get_git_commits` — commits for one profile and period;
- `prepare_youtrack_fill` — builds a per-issue YouTrack plan, never writes;
- `write_plan` — executes a plan only after explicit elicitation approval.

Flow is read → prepare → `write_plan` approval:

1. `prepare_youtrack_fill` validates dates, hours, issue IDs and commit hashes,
   then stores a one-time plan (`plan_id`, 10-minute TTL). It returns entries
   and warnings but performs no POST and calls no AI.
2. `write_plan` claims the plan, asks for `approved: true`, rechecks freshness
   and then writes. Missing approval, unknown/replayed/expired plans and clients
   without elicitation support all return `{"status": "blocked"}`.

YouTrack fill rules:

- Period defaults to the 1st of the current month through today.
- Issue is per entry (`DRIVEO-XXXX` from commit subject/body). If no referenced
  commit mentions the issue, the plan is still created with a warning.
- Daily meeting uses `youtrack.daily_meeting_issue_id` for
  `youtrack.daily_meeting_hours` (default `1.0`) on Mon–Fri, and is rejected if
  that date already has a worklog for the issue. Other entries require commit
  hashes.
- Hours are positive multiples of `0.5`; proposed plus existing daily hours
  must not exceed 8.
- Redmine MCP scenarios are not implemented in this phase; Redmine remains
  GUI-only. The server needs no AI keys.

Security rules:

- `config/users.json` holds tokens, is git-ignored and must stay `0600`. Only
  `config/users.example.json` with blank placeholders is tracked.
- Tool output, errors and logs must never contain access tokens, API keys or
  authorization headers.
- Tests use in-memory MCP clients, fakes and Git fixtures; they must not make
  live tracker requests or write to real trackers.

## Environment Variables

- Never commit secrets to version control
- Use `.env` files for local development (already in `.gitignore`)
- Document required variables in `.env.example`

Required variables:
- `REDMINE_BASE_URL` — Redmine instance URL (GUI only)
- `YOUTRACK_BASE_URL` — YouTrack instance URL (GUI and MCP server)
- `WORK_ASSISTANT_DB` — optional path to the SQLite database
  (`FILL_REDMINE_DB` is still accepted as a legacy alias)

Tracker keys, AI provider keys and models are stored in SQLite for the GUI, not
in env. The MCP server reads profiles and tokens from `config/users.json`.

## Making Changes

1. Run the GUI (`python work_assistant.py`) and test the flow manually
2. Run `pytest` to verify the suite is green
3. If adding ruff, run `ruff check . && ruff format .` before committing
4. Each task ends with green tests and its own commit

The MCP catalog is asserted in `tests/test_mcp_server.py` (five tools, no
prompts/resources/instructions). Keep it in sync when adding tools.
