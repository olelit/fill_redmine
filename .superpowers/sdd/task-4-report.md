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

## Reviewer fixes

### RED/GREEN cycles

1. **Changed destination profile refusal**
   - RED: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
     tests/test_mcp_write_tools.py -q -k 'duplicate_entry_dates or changed_target_config'` — the
     target-change case proceeded into `build_user_tracker` and errored when its stub returned
     `None`, demonstrating the missing pre-call refusal.
   - GREEN: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
     tests/test_mcp_write_tools.py -q -k changed_target_config` — `1 passed, 17 deselected`.
   - Added SHA-256 over compact, sorted JSON of only the destination block. The plan field is
     excluded from repr; `execute_plan` recomputes after profile reload and rejects mismatch before
     constructing a tracker. A test also verifies key-order stability, target-only scope, and repr
     exclusion.
2. **Duplicate entry-date rejection**
   - RED: same RED command — `test_plan_store_rejects_duplicate_entry_dates` failed because duplicate
     dates did not raise `ValueError`.
   - GREEN: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
     tests/test_mcp_write_tools.py -q -k duplicate_entry_dates` — `1 passed, 17 deselected`.
   - `PlanStore.create` now checks date uniqueness before storing the plan.

### Verification

- Focused: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest
  tests/test_mcp_write_tools.py -q` — `18 passed`; no warnings.
- Full: `/tmp/opencode/work-assistant-mcp-venv/bin/python -m pytest -q` — `274 passed`; no warnings.
- `git diff --check` — no output.

### Files and self-review

- `mcp_server/plans.py`: fingerprint field hidden from repr, canonical target-block fingerprint,
  duplicate-date validation; existing one-use and 600-second expiry behavior unchanged.
- `mcp_server/writer.py`: fresh enabled-profile fingerprint comparison before any tracker
  construction/call; no raw credentials are copied into plans.
- `tests/test_mcp_write_tools.py`: RED cases, target-only/canonical fingerprint coverage, and updated
  plan fixtures.
- `.superpowers/sdd/task-4-report.md`: this reviewer-fix record.
- No fingerprint is included in tool results, elicitation text, repr, or logging. Tracker writes
  remain behind the existing approval gate; results still expose only per-row status.
- Commit: `fix: bind MCP write plans to target profiles`.
- Self-review found no outstanding concerns. No GUI or live tracker requests were run.
