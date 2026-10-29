# Task 3 report: `prepare_youtrack_fill` from commits

## Status

DONE. Tests green; commit created after this report.

## What changed

### `mcp_server/youtrack_tools.py` (new)

- Added `SuggestedEntry` Pydantic model with `date`, `issue_id`, `hours`,
  `comment`, `commit_hashes`.
- Added `register_youtrack_tools(server, users_path, plans)` which registers the
  `prepare_youtrack_fill` MCP tool against the injected `PlanStore`.
- `prepare_youtrack_fill`:
  - defaults the period to the first day of the current month through today
    (`_default_period`, `_period`);
  - loads the enabled profile, reads YouTrack worklogs through the existing
    `build_user_tracker(profile, "youtrack")` adapter, and commits through the
    existing `GitClient(repo_path).list_commits(profile.git_email, ...)`;
  - validates every suggested entry and creates a per-issue `WritePlan` with an
    empty plan-level issue (`issue_id=""`) because each entry carries its own
    normalized issue;
  - never calls `create_worklogs` and never invokes AI;
  - returns `status`, `plan_id`, `user`, `period`, `entries`, `warnings`.
- Validation:
  - ISO `YYYY-MM-DD` dates inside the requested period;
  - issues normalized with `strip().upper()` and matched against
    `^[A-Z][A-Z0-9]+-\d+$`;
  - positive hours in 0.5 increments;
  - non-blank comments;
  - every hash must exist among the author's commits and belong to the row's
    author date;
  - warning `"<date>: issue <ID> not found in commit subjects"` when the issue
    is absent from the subject/body of the row's referenced commits;
  - duplicate `(date, issue)` rejected;
  - proposed + existing hours per day capped at 8.
- Daily meeting:
  - reads `youtrack.daily_meeting_issue_id` and
    `youtrack.daily_meeting_hours` (default `1.0`);
  - allows empty `commit_hashes` only when the issue matches the configured
    daily issue, the hours match the configured value, and the date is Mon–Fri;
  - rejects an already-recorded daily meeting for the same date;
  - rejects hash-less rows when daily meeting is not configured, and hash-less
    non-daily rows in all cases.
- `GitError` is converted to the generic safe `ToolError("Git commit read
  failed")`; `ProfileConfigError`, validation errors, and `ValueError` are
  converted to `ToolError` without including profile values or tokens.

### `mcp_server/app.py`

Registers `prepare_youtrack_tools` after the read tools and before
`write_plan`, reusing the same `PlanStore` instance. Catalog order is now:

`list_enabled_users`, `get_worklogs`, `get_git_commits`,
`prepare_youtrack_fill`, `write_plan`.

### Tests

- `tests/test_mcp_youtrack_tools.py` (new, 23 cases) covers:
  - a valid plan with two issues on one day, existing 1 h + proposed 7 h, plan
    creation, normalized entries, no `create_worklogs` calls, no token in the
    response;
  - issue present in commit subject; issue absent (warning); issue in commit
    body with lowercase input normalization;
  - daily meeting accepted, daily hours defaulting to 1.0, and daily meeting
    rejection for wrong hours / weekend / missing config / already recorded;
  - errors for no commits, unknown hash, hash from another date, non-0.5 hours,
    daily total above 8 h (with existing hours), duplicate `(date, issue)`,
    blank comment, invalid issue, out-of-period date, non-ISO date;
  - default-month helper and a tool call with omitted `start`/`end`;
  - token hygiene on success and errors.
- `tests/test_mcp_server.py` and `tests/test_mcp_read_tools.py`: expected
  catalog updated to include `prepare_youtrack_fill` (the latter also asserts
  the exact catalog and would otherwise fail).

## TDD evidence

### RED

```text
$ .venv/bin/python -m pytest tests/test_mcp_youtrack_tools.py -q
==================================== ERRORS ====================================
______________ ERROR collecting tests/test_mcp_youtrack_tools.py _______________
ImportError while importing test module '.../tests/test_mcp_youtrack_tools.py'.
...
tests/test_mcp_youtrack_tools.py:13: in <module>
    from mcp_server.youtrack_tools import _default_period
E   ModuleNotFoundError: No module named 'mcp_server.youtrack_tools'
!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!
1 error in 1.31s
```

The catalog assertions in `tests/test_mcp_server.py` and
`tests/test_mcp_read_tools.py` were also updated before implementation and
failed against the old four-tool server.

### GREEN (focused)

```text
$ .venv/bin/python -m pytest tests/test_mcp_youtrack_tools.py -q
23 passed in 1.28s
```

After the catalog updates:

```text
$ .venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_read_tools.py -q
24 passed in 1.26s
```

### GREEN (full suite)

```text
$ .venv/bin/python -m pytest -q
306 passed in 2.20s
```

Baseline before this task was 283 passing tests; 23 new tests were added.

`git diff --check` produced no output.

## Files changed

- `mcp_server/youtrack_tools.py` (new)
- `mcp_server/app.py`
- `tests/test_mcp_youtrack_tools.py` (new)
- `tests/test_mcp_server.py`
- `tests/test_mcp_read_tools.py`
- `.superpowers/sdd/task-3-report.md` (this report)

No GUI, Redmine, tracker, or writer files were modified. No live HTTP calls or
tracker writes are performed by the tests; `GitClient` and `build_user_tracker`
are replaced with fakes.

## Self-review

- The new tool reuses `PlanStore.create`, `PlannedEntry`,
  `fingerprint_target_config`, `GitClient`, and `build_user_tracker` rather than
  duplicating plan or tracker logic.
- The plan fingerprint covers the full `youtrack` profile block (token plus
  daily meeting settings), so `write_plan` still refuses changed configuration.
- Per-entry issues are normalized before entering `PlanStore`, matching the
  uniqueness key used there (`(date, issue)`), so the store cannot raise a
  duplicate `ValueError` after our own duplicate check.
- The issue-in-commit check is scoped to the commits explicitly referenced by
  the row. A row that references only unrelated commits gets the required
  warning; a daily meeting row without hashes skips the check.
- `_default_period` is a small pure helper and is tested directly, while a second
  test exercises the tool with omitted `start`/`end` using today's date.
- Credential hygiene: success payloads and every tested error path are asserted
  not to contain the profile token. Git errors are replaced with a generic
  message; configuration/validation messages contain only dates, issue IDs,
  hashes, and field descriptions.
- The tool is registered with the same `PlanStore` passed to `write_plan`, so a
  `plan_id` returned by `prepare_youtrack_fill` can be claimed by `write_plan`.
- Tests confirm `create_worklogs` is never called; only `get_worklogs` is used.

## Concerns

1. **No commits means no plan, even for a daily-meeting-only day.** The brief
   lists "no commits" as an error, so the tool currently rejects the whole
   request when `GitClient` returns no commits for the period. If a future
   workflow needs to plan daily meetings alone on a period with no commits,
   that rule would need revisiting.
2. **Plan-level `issue_id` is intentionally empty.** Per-issue rows are the
   source of truth; `write_plan` already falls back per entry, and the writer
   rejects an empty issue only for entries that lack one. The approval payload
   will therefore show `"issue": ""` at plan level and the real issue per entry.
3. **Daily meeting hours must be a JSON number.** `daily_meeting_hours` is
   validated as an `int`/`float`; a string such as `"1.0"` is rejected as
   invalid configuration. This matches the documented config shape used by
   Task 4.
4. **Warning scope is the row's referenced commits**, not every commit in the
   period. This is the intended interpretation for assigning issues per row; a
   reviewer may prefer period-wide matching if that was the intent.