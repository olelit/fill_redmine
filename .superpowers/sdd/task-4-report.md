# Task 4: Project MCP config, catalog and docs

## What changed

### Catalog test (brief Steps 1–2)

`tests/test_mcp_server.py` already asserted the final five-tool order and empty
prompts/resources; Task 3's commit `67665dd` had kept the catalog green as its
brief required. No RED was available for the tool list: the focused command was
green before the change. I added the missing catalog assertion from the brief:
`client.instructions is None`, so the server is now checked for tools, prompts,
resources and instructions.

- Focused after edit: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
  → `5 passed in 0.94s`.

### MCP project config

`.opencode/opencode.json` now launches the project virtualenv:

- `command: [".venv/bin/python", "-m", "mcp_server"]`
- `cwd: "."`
- `codemode: false`
- `protocol: "legacy"`

No other keys changed.

### Example profile

`config/users.example.json` remains a single disabled `CHANGE_ME` profile with
blank credentials (still covered by
`test_example_config_is_tracked_and_disabled_without_usable_credentials`).
Added:

- `youtrack.daily_meeting_issue_id: ""`
- `youtrack.daily_meeting_hours: 1.0`
- `youtrack.issue_id: ""` documented as the optional fallback

`git_email` and `youtrack.access_token` are present and blank. No real
`config/users.json` was created and no token was written.

### README

New `## MCP-сервер (YouTrack fill)` section covering:

- install (`pip install -r requirements.txt`), `.env` with `YOUTRACK_BASE_URL`;
- `cp config/users.example.json config/users.json` + `chmod 600`, ignored file;
- project OpenCode config fragment and `opencode mcp list`;
- the five tools table and the `read → prepare → write_plan` approval order;
- default period = current month through today;
- per-issue `DRIVEO-XXXX` from commit subject/body and the no-tag warning;
- daily meeting 1 h per working day when not yet recorded;
- Redmine MCP scenarios not implemented in this phase;
- AI keys are not needed by the server.

The intro now mentions the local MCP server alongside the GUI.

### AGENTS.md

- Overview and structure updated with `mcp_server/` and `config/`.
- New `### Running the MCP server` commands, including `0600`, direct
  `python -m mcp_server`, project OpenCode config and `opencode mcp list`.
- New `## MCP Server` section: five tools, one-time 10-minute plans,
  fail-closed `write_plan`, youtrack fill rules, approval requirement, and
  secret-handling/testing rules.
- Environment variables annotated as GUI-only / GUI+MCP; noted profiles and
  tokens come from `config/users.json`.
- `Making Changes` notes the catalog assertion in `tests/test_mcp_server.py`.

### Task 3 review nits

- `mcp_server/youtrack_tools.py`: added trailing newline; removed the dead
  `today` parameter from `_period` (only `_default_period` keeps an injectable
  date for its test); annotated `_commits_by_hash`, `_commit_date` and
  `_existing_hours_by_date`, and tightened the related commit types from
  `object` to `GitCommitDTO` (`list[WorklogDTO]` for worklogs). No behavior
  changed.
- `tests/test_mcp_youtrack_tools.py`: added the missing trailing newline.

## Verification

| Command | Result |
| --- | --- |
| `.venv/bin/python -m pytest tests/test_mcp_server.py -q` | `5 passed` |
| `.venv/bin/python -m pytest tests/test_mcp_config.py tests/test_mcp_youtrack_tools.py tests/test_mcp_server.py -q` | `54 passed in 1.32s` |
| `.venv/bin/python -m pytest -q` | `306 passed in 2.21s` |
| `git diff --check` | no output |
| JSON parse of both config files | ok |

No warnings appeared in the pytest output.

Commit subject: `docs: document per-issue YouTrack MCP setup` (report included in
the same commit; the SHA is returned to the controller).

## Files changed

- `.opencode/opencode.json`
- `config/users.example.json`
- `README.md`
- `AGENTS.md`
- `mcp_server/youtrack_tools.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_youtrack_tools.py`
- `.superpowers/sdd/task-4-report.md` (this report; ignored by git)

## Self-review

- The documented tool list matches `create_server` exactly: five tools, no
  prompts/resources/instructions; the test proves it through the in-memory MCP
  client.
- README/AGENTS do not promise Redmine MCP support, AI usage, or any write path
  other than `write_plan` with approval.
- `config/users.json` is absent from the tree; the example keeps blank
  placeholders and stays loadable, so the config test still passes.
- `_period` has no remaining caller passing `today`; `_default_period` remains
  independently tested.
- The type changes are annotations only; the 306-test suite stayed green.
- No secret values were added to any tracked file or to the report.

## Concerns

- Brief Step 2 expected a failing catalog test, but the list was already
  finalized in Task 3 (`67665dd`), so that RED step could not be reproduced.
  The only new assertion (`instructions is None`) passed immediately on the
  unchanged server; it is a regression guard rather than a TDD cycle.
- `config/users.json` and `opencode mcp list` were not exercised with real
  credentials, by instruction. Actual connection verification is left to the
  controller's post-task live-fill step.