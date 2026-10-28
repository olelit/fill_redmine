# Task 3: Read-only MCP tracker and git tools

## TDD evidence

- Initial RED: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_read_tools.py -q`
  failed during collection with `ModuleNotFoundError: No module named 'mcp_server.read_tools'`,
  confirming the requested read tools were absent.
- Additional validation RED:
  `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_read_tools.py::test_tracker_adapter_rejects_blank_required_fields_without_exposing_credentials -q`
  failed all three cases because blank API/token/issue fields were accepted.
- Focused GREEN:
  `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_read_tools.py tests/test_git_client.py -q`
  — `20 passed in 1.07s`.
- Full GREEN: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest -q`
  — `249 passed in 1.43s`.
- `git diff --check` completed without output.

## Files changed

- `mcp_server/tracker_access.py`: clones per-user tracker settings; validates required read/write
  fields; injects only a supplied Redmine issue ID; validates the per-user Redmine comment.
- `mcp_server/read_tools.py`: adds tracker worklog and Git commit reads, strict date range and
  enabled-profile validation, credential-free metadata, and path-bound MCP tool registration.
- `mcp_server/app.py`: registers exactly `list_enabled_users`, `get_worklogs`, and
  `get_git_commits`.
- `tests/test_mcp_read_tools.py`: covers Redmine reads without a saved issue, YouTrack aggregation,
  Git metadata from a temporary repository, credentials, validation, cloning, and tool schemas.
- `tests/test_mcp_server.py`: updates the prior one-tool assertion to the required three-tool
  server surface.
- `.superpowers/sdd/task-3-report.md`: this report.

## Self-review

- Both read paths use existing read-only adapters (`get_worklogs` and `GitClient.list_commits`);
  neither invokes `create_worklogs` or uses a shell command string.
- Redmine's legacy generic `is_configured()` check is not used, so read access does not require an
  issue ID. The builder copies config before injecting a request-scoped issue for writes.
- MCP closures bind `users_path`; it is not exposed as a model-visible tool argument.
- Tracker and Git results omit tokens, API keys, and profile email. Tracker modules and their
  configuration contract were left unchanged.
- Commit: `feat: add read-only MCP tracker and git tools` (SHA is included in the completion
  response).

## Concerns

- No outstanding concerns. GUI/manual testing was not performed; the tools were verified through
  the in-memory MCP client and the full automated suite.

## Task 3 reviewer follow-up

### RED/GREEN evidence

- RED: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_read_tools.py -q`
  — `5 failed, 13 passed in 1.11s`. Four cases proved fractional Redmine IDs and booleans were
  accepted. The invalid-repository MCP case got the server's unexpected-tool fallback instead of
  the expected safe `Git commit read failed` tool error.
- GREEN focused: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
  tests/test_mcp_read_tools.py tests/test_git_client.py -q` — `27 passed in 1.10s`.
- GREEN full suite: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest -q` —
  `256 passed in 1.45s`.
- `git diff --check` completed without output.

### Files changed

- `mcp_server/tracker_access.py`: rejects bool and non-string/non-integer Redmine IDs while retaining
  positive integers and integer strings.
- `mcp_server/read_tools.py`: translates `GitError` from the registered Git tool to a generic safe
  `ToolError`.
- `tests/test_mcp_read_tools.py`: covers invalid/valid Redmine IDs and generic errors for invalid
  Git repository paths.
- `.superpowers/sdd/task-3-report.md`: this follow-up record.

### Self-review

- Invalid IDs return only the field name, never the supplied ID or credential. `int()` is still used
  for supported integer strings, but floats and booleans are rejected before conversion.
- Git reads remain through `GitClient.list_commits`; only `GitError` is translated, and its
  underlying path/email details are not sent to the tool caller. The Git client and tracker modules,
  registration, dependencies, and unrelated behavior were not changed.
- Implementation commit: `11d8928bb8a15e13191b12a462f7e8f4167ef929`.
- No outstanding concerns. GUI/manual testing was not performed; these changes were verified via
  unit tests and the in-memory MCP client.
