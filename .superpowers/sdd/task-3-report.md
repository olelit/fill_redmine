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
