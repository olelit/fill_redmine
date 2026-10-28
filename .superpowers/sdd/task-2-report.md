# Task 2: MCP stdio server and enabled-user tool

## TDD evidence

- RED: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_server.py -q`
  failed during collection as expected with `ModuleNotFoundError: No module named 'mcp'`;
  the SDK/server implementation was not present yet.
- Dependency installation initially exposed a resolver conflict: SDK 2.3 requires
  `idna>=3.18`, while the project pinned `idna==3.11`. Updated the pin to 3.18;
  `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pip install -r requirements.txt`
  then completed successfully with `mcp 2.3.0`.
- GREEN focused: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_config.py -q`
  — `31 passed, 1 warning`.
- GREEN full suite: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest -q`
  — `238 passed, 1 warning`.

## Files changed

- `mcp_server/app.py`: constructs `MCPServer("Work Assistant")` and registers only
  `list_enabled_users`, using the injected or default users path.
- `mcp_server/__main__.py`: starts stdio transport only under the `__main__` guard.
- `mcp_server/user_tools.py`: reloads profiles when called, filters enabled users,
  returns only names and configured tracker kinds, and converts safe config errors
  to MCP tool errors.
- `.opencode/opencode.json`: adds the requested local MCP server configuration.
- `requirements.txt`: adds `mcp>=2.3,<3`; updates `idna` to satisfy the SDK's
  transitive dependency.
- `tests/test_mcp_server.py`: tests enabled-user results, disabled filtering,
  credential exclusion, tool registration/no prompts or resources, and missing-file
  error handling through the in-memory SDK client.
- `.superpowers/sdd/task-2-report.md`: records this report.

## Self-review

- The server registers exactly the one tool required at this task stage. It adds no
  prompts, resources, or custom instructions.
- The tool reloads the config on each invocation and does not serialize profile
  fields or include config contents in errors.
- The OpenCode config matches the required structure and contains no secrets.
- Commit: `feat: bootstrap local Work Assistant MCP server`.

## Concerns

- The brief specifies `list[dict[str, str]]` but not its exact keys or tracker
  encoding. The implementation returns `{"name": ..., "trackers": ...}` with
  tracker kinds comma-separated (empty string when none are configured).
- Pytest reports an existing AnyIO deprecation warning (`CallSpec2` renamed to
  `CallSpec`); all tests pass.
