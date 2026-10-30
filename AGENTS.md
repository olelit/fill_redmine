# AGENTS.md

This file provides guidance for agents working on this codebase.

## Project Overview

Work Assistant is a local MCP stdio server for time tracking. It reads worklogs
from Redmine and YouTrack and commits from git, builds write plans, and writes
hours only after explicit MCP elicitation approval. GUI and CLI entry points
have been removed; MCP is the only supported interface. It uses:

- `mcp` for the local stdio server;
- `requests` for sync HTTP requests;
- `python-dotenv` for environment variables.

## Project Structure

```text
fill_redmine/
├── mcp_server/              # Local stdio MCP server
│   ├── __main__.py          # `python -m mcp_server`
│   ├── app.py               # create_server: tool registration
│   ├── config.py            # JSON user profiles (config/users.json)
│   ├── user_tools.py        # list_enabled_users
│   ├── read_tools.py        # get_worklogs, get_git_commits
│   ├── tracker_access.py    # profile -> tracker construction
│   ├── youtrack_tools.py    # prepare_youtrack_fill
│   ├── transfer_tools.py    # prepare_youtrack_transfer
│   ├── periods.py           # period parsing
│   ├── plans.py             # one-time write plans
│   ├── write_tools.py       # write_plan approval gate
│   └── writer.py            # approved plan execution
├── clients/                 # HTTP and git clients
│   ├── redmine_client.py
│   ├── youtrack_client.py
│   └── git_client.py
├── configs/config.py        # REDMINE_BASE_URL / YOUTRACK_BASE_URL
├── dto/                     # GitCommitDTO, WorklogDTO
├── trackers/                # BaseTracker + Redmine/YouTrack adapters
├── config/
│   ├── users.example.json
│   └── users.json           # ignored, 0600, real tokens
└── tests/                   # pytest suite
```

## Build/Run Commands

### Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
cp config/users.example.json config/users.json
chmod 600 config/users.json
```

Fill `REDMINE_BASE_URL`, `YOUTRACK_BASE_URL`, and the profile tokens in
`config/users.json`.

### Running the MCP server

```bash
.venv/bin/python -m mcp_server
```

OpenCode starts it automatically from `.opencode/opencode.json`. Verify with
`opencode mcp list` (expect `work-assistant connected`).

### Testing

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/pytest tests/test_mcp_server.py -v
.venv/bin/pytest -k "mcp"
```

### Linting and Formatting

The project has no linting configuration. If ruff is added:

```bash
ruff check .
ruff format .
```

## Code Style Guidelines

### Imports

Use absolute imports and order stdlib → third-party → local project:

```python
import os

from dotenv import load_dotenv

from configs.config import Config
from dto.worklog_dto import WorklogDTO
```

### Type Annotations

Use type hints for parameters and return types. Prefer built-in types and `|`
unions (Python 3.10+).

```python
def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
    ...

def create_worklogs(self, records: list[WorklogDTO]) -> list[tuple[str, str]]:
    ...
```

### Naming

- Classes: PascalCase
- Functions/variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Private methods: `_prefix`

### Dataclasses

Use `@dataclass` for DTOs and plans.

### Error Handling

Use specific exceptions, `response.raise_for_status()` or explicit status
checks, and never include tokens or authorization headers in messages.

### User-Facing Strings

MCP tool results and approval text are mostly Russian; technical identifiers
stay in English.

### Formatting

Use f-strings, 4 spaces, max 100 characters per line.

## MCP Server

`mcp_server/` exposes exactly six tools and no prompts/resources:

- `list_enabled_users` — enabled profile names and tracker kinds;
- `get_worklogs` — worklogs for one profile and period;
- `get_git_commits` — commits for one profile and period;
- `prepare_youtrack_fill` — builds a per-issue YouTrack plan, never writes;
- `prepare_youtrack_transfer` — builds a YouTrack → Redmine plan, never writes;
- `write_plan` — executes a plan only after explicit elicitation approval.

Flow is read → prepare → `write_plan` approval. Plans are one-time, in-memory
and expire after 10 minutes. Missing approval, unknown/replayed/expired plans
and clients without elicitation support return `{"status": "blocked"}`.

YouTrack fill rules:

- Period defaults to the 1st of the current month through today.
- Issue is per entry (`DRIVEO-XXXX` from commit subject/body). If no referenced
  commit mentions the issue, the plan is created with a warning.
- Daily meeting uses `youtrack.daily_meeting_issue_id` for
  `youtrack.daily_meeting_hours` (default `1.0`) on Mon–Fri.
- `youtrack.issue_id` is the fallback for stretching a day to 8 hours when
  there are no commits.
- Hours are positive multiples of `0.5`; proposed plus existing daily hours
  must not exceed 8.
- YouTrack work item dates use UTC midnight.

YouTrack → Redmine transfer rules:

- `prepare_youtrack_transfer` accepts a required positive Redmine `issue_id`;
  the ID is never read from JSON.
- Period defaults to the 1st of the current month through today.
- Worklogs are summed per date; one Redmine entry is created per date.
- The Redmine comment is exactly `redmine.comment`; source issue IDs are never
  appended.
- For every source date, all of the user's existing Redmine time entries are
  recorded and deleted after approval, then replaced by the new entry. Dates
  without YouTrack worklogs are left untouched.
- `prepare_youtrack_transfer` performs no POST/DELETE. `write_plan` performs
  all deletions and creations only after explicit approval.
- If deletion fails for a date, no new entry is created for that date; other
  dates still proceed.
- Deletion and creation are not transactional: if deletion succeeds but
  creation fails, the old entry is already gone; the result is marked `failed`
  with `create_failed`.

Security rules:

- `config/users.json` holds tokens, is git-ignored and must stay `0600`. Only
  `config/users.example.json` with blank placeholders is tracked.
- Tool output, errors and logs must never contain access tokens, API keys or
  authorization headers.
- Tests use in-memory MCP clients, fakes and Git fixtures; they must not make
  live tracker requests or write to real trackers.

## Environment Variables

Required:

- `REDMINE_BASE_URL` — Redmine instance URL;
- `YOUTRACK_BASE_URL` — YouTrack instance URL.

Tracker keys and models are not read from env. The MCP server reads profiles
and tokens from `config/users.json`.

## Making Changes

1. Run `.venv/bin/pytest -q`.
2. Update the MCP tests when changing tool contracts.
3. Keep the catalog at six tools, no prompts/resources/instructions.
4. Each task ends with green tests and its own commit.
