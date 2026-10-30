# Commit-Based Today Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an MCP tool that tracks today (or a requested period) in YouTrack from git commits, allocating 8 hours per day proportionally to commit intervals.

**Architecture:** A pure allocation module turns one day of commits into issue-level half-hour allocations. A new MCP tool reads existing YouTrack worklogs and commits, reserves the daily meeting, calls the allocator, and stores a normal one-time `WritePlan`. `write_plan` and elicitation are unchanged.

**Tech Stack:** Python 3.10+, `mcp` SDK, `pytest`, existing `GitClient`, `YoutrackTracker`, `PlanStore`.

## Global Constraints

- MCP server keeps no prompts/resources/instructions. Only tools.
- `prepare_*` tools never POST/DELETE. Writes happen only through `write_plan` after elicitation approval.
- Tool output and errors must never contain tokens, API keys, or auth headers.
- Hours per day must not exceed 8 after adding existing worklogs.
- YouTrack work item dates stay UTC midnight (writer/client already does this).
- Tests use fakes/tmp_path; no live tracker or git network calls.
- User-facing text is Russian; identifiers stay English.
- Every task ends with green tests and its own commit.
- No unrelated refactoring.

---

### Task 1: Commit interval allocator

**Files:**
- Create: `mcp_server/commit_allocation.py`
- Test: `tests/test_commit_allocation.py`

**Interfaces:**
- Consumes: `dto.git_commit_dto.GitCommitDTO` with `hash`, `date` (ISO string), `subject`, `body`.
- Produces:
  - `DEFAULT_WORKDAY_START: time = time(9, 0)`
  - `class AllocationError(ValueError)`
  - `@dataclass(frozen=True) class CommitAllocation: issue: str; hours: float; comment: str; commit_hashes: tuple[str, ...]; weight_minutes: float`
  - `@dataclass(frozen=True) class AllocationResult: allocations: tuple[CommitAllocation, ...]; warnings: tuple[str, ...]`
  - `def find_issue_ids(text: str) -> tuple[str, ...]`
  - `def allocate_commit_hours(commits: list[GitCommitDTO], *, day: date, hours: float, workday_start: time = DEFAULT_WORKDAY_START, fallback_issue: str | None = None, fallback_comment: str = "development") -> AllocationResult`

**Required behavior:**

1. `find_issue_ids` returns unique uppercase IDs matching `[A-Z][A-Z0-9]+-\d+` in order of appearance, case-insensitive. It must not match inside a longer token (use lookarounds).
2. Parse each commit date with `datetime.fromisoformat`; strip tzinfo for wall-clock comparison. Invalid date or different calendar day raises `AllocationError`.
3. Sort commits by wall-clock time.
4. `cursor` starts at `workday_start` in minutes. For each commit:
   - `weight = max(1.0, commit_minutes - cursor)`
   - update `cursor = max(cursor, commit_minutes)`
5. Issues for a commit come from `find_issue_ids(subject + "\n" + body)`. If none, use `fallback_issue`; if still none, append a warning and skip that commit.
6. If a commit has several issues, split its weight equally.
7. Aggregate weight, commit hashes (chronological, unique), and latest subject per issue.
8. `target_units = floor(hours * 2 + 1e-9)`. If `target_units <= 0`, return empty with warning.
9. Sort issues by weight descending, then first appearance. If `target_units < len(issues)`, keep the top `target_units`, warn about dropped issues.
10. Otherwise start each kept issue at 1 unit and distribute `target_units - len(issues)` extra units by largest remainder. Sum must be exactly `target_units`.
11. `hours = units / 2`; comment is the latest commit subject (fallback comment if blank), truncated to 255 chars.
12. `AllocationResult.warnings` are day-scoped plain strings without secrets.

**Tests:**
- `test_allocates_proportionally_to_commit_intervals`: A 10:00, B 13:30, A 17:00, 8h -> A 4.5, B 3.5.
- `test_splits_commit_between_multiple_issues`: one 10:00 commit references A and B, 8h -> 4/4.
- `test_uses_fallback_for_commit_without_issue`: no tag + fallback F -> F 8.
- `test_rounds_to_half_hours_and_sums_exactly`: weights do not divide evenly; sum is 8 and every hours * 2 is integer.
- `test_drops_lowest_weight_issue_when_hours_too_small`: 3 issues, 0.5h -> one entry, warning.
- `test_minimum_weight_keeps_zero_interval_commit`: same time A/B -> 4/4.
- `test_invalid_commit_date_raises`.
- `test_empty_commits_returns_empty`.

**Steps:**
- [ ] Write failing tests.
- [ ] Run `pytest tests/test_commit_allocation.py -q` and confirm failure.
- [ ] Implement module.
- [ ] Run test file, then full suite.
- [ ] Commit `feat: allocate daily hours from commit intervals`.

---

### Task 2: MCP tool `prepare_youtrack_from_commits`

**Files:**
- Create: `mcp_server/commit_tools.py`
- Modify: `mcp_server/app.py`
- Modify: `tests/test_mcp_server.py` (tool list)
- Test: `tests/test_mcp_commit_tools.py`

**Interfaces:**
- Consumes: `allocate_commit_hours`, `AllocationError`, `AllocationResult` from Task 1.
- Consumes existing helpers from `mcp_server.youtrack_tools`: `MAX_DAILY_HOURS`, `HOURS_TOLERANCE`, `YoutrackFillError`, `_daily_meeting_config`, `_fallback_issue`, `_normalize_issue`.
- Produces:
  - `def register_commit_tools(server: MCPServer, users_path: Path, plans: PlanStore) -> None`
  - MCP tool name `prepare_youtrack_from_commits`.

**Tool contract:**

```text
prepare_youtrack_from_commits(
    user_name: str,
    repo_path: str,
    start: str | None = None,
    end: str | None = None,
    daily_hours: float = 8.0,
) -> dict
```

- `start`/`end` default to today (not the first of month).
- Validate `daily_hours`: finite, > 0, <= 8.
- Read profile, daily meeting config, fallback issue, and `youtrack.default_comment` (default `"development"`), `youtrack.workday_start` (default `"09:00"`, parse `HH:MM`).
- Build YouTrack tracker and read existing worklogs for the period.
- Read commits via `GitClient(repo_path).list_commits(profile.git_email, start, end)`.
- Group commits by calendar date (strip tzinfo).
- For each date in the period:
  - `remaining = daily_hours - existing_hours_for_date`; if <= tolerance, warning and skip.
  - If daily meeting configured, weekday, not already recorded that date, and `remaining >= daily_hours_meeting`, add `PlannedEntry(day, meeting_hours, "Daily meeting", (), daily_issue)` and subtract.
  - If commits: call allocator with `hours=remaining`, `day=date`, `workday_start`, `fallback_issue`, `fallback_comment=default_comment`.
    - Add allocations as `PlannedEntry(date, hours, comment, commit_hashes, issue)`.
    - If allocator returns none and fallback exists, add one fallback entry for all remaining hours with all day's commit hashes and a warning.
    - If no fallback, warning and skip.
  - If no commits: fallback entry with remaining hours and empty hashes + warning; else warning and skip.
- Merge duplicate `(date, issue)` entries by summing hours, unioning hashes, and joining unique comments with `"; "` (cap 255).
- If no entries remain, raise `YoutrackFillError` with a clear message.
- Create plan with `destination_kind="youtrack"`, `issue_id=""`, `fingerprint_target_config(profile, "youtrack")`.
- Return `status`, `plan_id`, `user`, `period`, `entries` (same shape as fill tool), `warnings`, and `daily_hours`.
- Register with a Russian description explaining: today by default, 8h default, proportional commit intervals, no writes, use `write_plan` to write.

**Tests:**
- `test_prepare_today_defaults_to_today_and_eight_hours`: today's commits, no dates -> entries sum 8, period today..today.
- `test_prepare_respects_existing_hours_and_daily_meeting`: existing 2h + meeting 1h + commits -> planned + existing == 8, meeting entry present.
- `test_prepare_uses_fallback_when_no_commits`: no commits + fallback -> 8h fallback entry.
- `test_prepare_explicit_period_tracks_each_day`.
- `test_prepare_does_not_write`: fake tracker writes list stays empty.
- `test_prepare_rejects_invalid_daily_hours` (0, -1, 9, NaN).
- `test_prepare_skips_full_day`.
- `test_prepare_rejects_no_commits_without_fallback`.
- `test_prepare_merges_issue_seen_in_multiple_commits`.
- `test_server_lists_new_tool`.
- Keep secrets out of output assertion.

**Steps:**
- [ ] Write failing tests.
- [ ] Run and confirm failure.
- [ ] Implement module and registration.
- [ ] Run targeted tests, then full suite.
- [ ] Commit `feat: add commit-based YouTrack tracking tool`.

---

### Task 3: Documentation and agent routing

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `config/users.example.json`
- Maybe create: `.opencode/command/track-today.md` if the format is confirmed; otherwise skip.

**Required updates:**
- Tool table goes from six to seven and documents `prepare_youtrack_from_commits`.
- New section explains today mode, 8h default, interval algorithm, workday_start/default_comment, existing hours, daily meeting.
- AGENTS.md: repository name `work-assistant`; add rule: any request to track from commits must use `prepare_youtrack_from_commits`, never manual allocation; today request means no dates.
- Example config adds `"workday_start": "09:00"`, `"default_comment": "development"`.
- Historical docs under `docs/superpowers/` are not rewritten.

**Steps:**
- [ ] Update docs.
- [ ] Run `pytest -q` (docs only, must stay green).
- [ ] Commit `docs: document commit-based daily tracking`.

---

### Task 4: Rename repository and final verification

**Files:**
- Rename directory `/home/oleg/code/fill_redmine` -> `/home/oleg/code/work-assistant`.
- Update `AGENTS.md` structure path and `README.md` if any old path remains.
- Update remote URL only after GitHub rename; otherwise leave `origin` and report the pending manual step.
- Verify `.venv/bin/python -m pytest -q` still works after the move. If the venv shebang broke, recreate it or use the system Python with the venv's site-packages.

**Steps:**
- [ ] Check for remaining `fill_redmine` references outside historical docs.
- [ ] Rename local directory.
- [ ] Move the OpenCode session to the new directory.
- [ ] Run full test suite from the new path.
- [ ] Commit any path fixes.
- [ ] Report GitHub rename as the only manual step if no token/gh is available.

---

### Final review

- [ ] Run `pytest -q`.
- [ ] Inspect `git diff main...HEAD`.
- [ ] Verify no secrets in outputs.
- [ ] Verify new tool is listed and old six remain.
- [ ] Merge branch to `main` if green, or leave branch for user review.