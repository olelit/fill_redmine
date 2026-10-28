# Task 4: Immutable plans and fail-closed elicitation writes

## RED/GREEN evidence

- RED: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest tests/test_mcp_write_tools.py -q`
  failed collection with `ModuleNotFoundError: No module named 'mcp_server.plans'`, confirming the
  plan-store/write-gate implementation was absent.
- Focused GREEN: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
  tests/test_mcp_write_tools.py -q` — `15 passed in 1.09s`.
- Focused integration: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
  tests/test_mcp_write_tools.py tests/test_mcp_read_tools.py tests/test_mcp_server.py -q` —
  `37 passed in 1.26s` (before the final executor-error regression test was added).
- Full GREEN: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest -q` —
  `271 passed in 1.67s`; default output contained no warnings.
- `git diff --check` completed without output.

## Files changed

- `mcp_server/plans.py`: frozen plan/entry models, random IDs, one-time atomic claims, monotonic
  600-second expiry, and post-elicitation freshness validation.
- `mcp_server/write_tools.py`: registers `write_plan`, uses a flat one-boolean Pydantic approval
  form, claims before prompting, blocks unsupported/declined/canceled/false/expired requests, and
  leaves executor errors uncaught.
- `mcp_server/writer.py`: reloads and validates the enabled profile at write time, injects the
  approved Redmine issue ID or verifies the current YouTrack issue, and returns credential-free
  per-entry statuses.
- `mcp_server/app.py`: registers the write gate with a per-server plan store and path-bound writer.
- `tests/test_mcp_write_tools.py`: covers plan lifecycle, legacy-mode in-memory elicitation outcomes,
  approval schema and message safety, freshness/replay, profile reload, issue checks, statuses, and
  executor errors. All tracker writers are injected fakes; no live HTTP writes are made.
- `tests/test_mcp_read_tools.py`, `tests/test_mcp_server.py`: update expected tool registration to
  include the new write gate.
- `.superpowers/sdd/task-4-report.md`: this report.

## Self-review

- The only MCP tool that calls the writer is `write_plan`; read tools remain unchanged and do not
  invoke `create_worklogs`.
- The plan and elicitation contain only approved worklog data, not profile credentials. The writer
  reads profile secrets only after approval, and response rows expose only dates and status labels.
- Claims remove plans before elicitation, preventing replay and concurrent duplicate claims. The
  second TTL check occurs after approval and before invoking the executor.
- Tracker write failures are not caught or transformed into approval results.
- Commit: `feat: require MCP elicitation for worklog writes`.

## Concerns

- No outstanding concerns. GUI/manual testing was not performed; write behavior was tested with
  injected fakes through the in-memory MCP client, with no live network writes.
