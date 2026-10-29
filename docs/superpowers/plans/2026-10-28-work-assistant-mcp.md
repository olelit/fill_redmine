# Work Assistant MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` to implement this plan task-by-task. This repository requires a fresh subagent per task and review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local MCP server that prepares and safely writes the three approved worklog scenarios from a git-ignored JSON user config.

**Architecture:** Use the official MCP Python SDK v2 over stdio. Dedicated MCP tools read profiles, tracker worklogs and git commits; prepare tools create immutable, in-memory write plans; a single write tool asks for explicit MCP elicitation and only then calls existing tracker clients. The agent's own model analyzes commit context, so the server needs no AI credentials.

**Tech Stack:** Python 3.10+, `mcp>=2.3,<3`, `requests`, existing Redmine/YouTrack clients and `GitClient`, pytest, OpenCode V2 local MCP configuration.

## Global Constraints

- MCP transport is local stdio; OpenCode config sets `protocol: "legacy"` for SDK elicitation and `codemode: false` for direct tools.
- User credentials are read from `config/users.json`, which must be git-ignored; `is_enable: false` profiles are never selectable or used.
- MCP responses and logs never include tracker credentials or authorization headers.
- Redmine `issue_id` is required from the current request in both Redmine write scenarios; never use a saved Redmine issue ID.
- The MCP server does not call an AI provider, expose arbitrary shell/HTTP/write tools, define prompts/resources/instructions, or invoke skills/subagents/other MCP servers.
- Every write is represented by a one-use plan and is blocked on elicitation decline, cancellation, timeout, or unsupported-client error.
- Commit analysis receives repo path per request; it is validated as a Git worktree and read with the existing `GitClient` only.
- No live write calls are used in tests or verification; mock tracker clients and HTTP requests.

---

## File Map

- `mcp_server/config.py` — JSON schema parsing, enabled-profile filtering, profile selection.
- `mcp_server/tracker_access.py` — construct tracker adapters without exposing secrets; validate operation-specific credentials.
- `mcp_server/app.py`, `mcp_server/__main__.py` — build/run MCP and register the declared tools only.
- `mcp_server/user_tools.py`, `mcp_server/read_tools.py` — safe user list and read-only worklog/commit tools.
- `mcp_server/plans.py` — immutable plan entries and one-use, expiring in-memory plan store.
- `mcp_server/write_tools.py`, `mcp_server/writer.py` — MCP elicitation and the only path to `create_worklogs`.
- `mcp_server/redmine_tools.py` — Redmine autofill and YouTrack-to-Redmine transfer preparation.
- `mcp_server/youtrack_tools.py` — agent-proposed YouTrack completion preparation and validation.
- `config/users.example.json` — non-secret config template; actual `config/users.json` stays ignored.
- `.opencode/opencode.json` — project-local OpenCode connection using direct tools and legacy protocol.
- `tests/test_mcp_*.py` — isolated config, tool, plan, and workflow tests.

Existing files that may change:

- `.gitignore`, `requirements.txt`, `README.md`, `AGENTS.md` — ignore config, install/document the server.
- `mcp_server/app.py` — register each task's tools with the server.

## Task 1: Add the JSON profile loader

**Files:**
- Create: `mcp_server/__init__.py`
- Create: `mcp_server/config.py`
- Create: `config/users.example.json`
- Create: `tests/test_mcp_config.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces `UserProfile`, `ProfileConfigError`, `default_users_path() -> Path`, `load_users(path: Path | None = None) -> list[UserProfile]`, and `select_user(users: list[UserProfile], name: str | None = None) -> UserProfile`.
- A profile contains `name`, `is_enable`, `git_email`, `redmine`, and `youtrack`; secret mappings use `repr=False` and are never part of public summaries.
- `load_users` reads `<repo>/config/users.json` by default, validates the root `users` array and profile structural types, and does not execute Python or print file contents.
- Tracker-specific required fields are checked at operation time, so a profile may omit a tracker it does not use.

- [ ] **Step 1: Add failing profile-loader tests**

```python
import json

import pytest

from mcp_server.config import ProfileConfigError, load_users, select_user


def test_load_users_filters_disabled_and_selects_only_enabled(tmp_path):
    path = tmp_path / "users.json"
    path.write_text(
        json.dumps(
            {
                "users": [
                    {"name": "disabled", "is_enable": False},
                    {"name": "Oleg", "is_enable": True, "git_email": "o@example.com"},
                ]
            }
        ),
        encoding="utf-8",
    )

    users = load_users(path)

    assert [user.name for user in users if user.is_enable] == ["Oleg"]
    assert select_user(users).name == "Oleg"


def test_load_users_rejects_invalid_root(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(ProfileConfigError):
        load_users(path)
```

- [ ] **Step 2: Run the test and confirm the missing-module failure**

Run: `pytest tests/test_mcp_config.py -q`  
Expected: FAIL because `mcp_server.config` does not exist.

- [ ] **Step 3: Implement the loader and ignored example config**

Use a frozen dataclass; make secret mappings non-repr fields. Reject malformed JSON, a missing/non-list `users`, blank names, and non-boolean `is_enable`. Ignore `config/users.json` (not the example) in `.gitignore`.

```python
@dataclass(frozen=True)
class UserProfile:
    name: str
    is_enable: bool
    git_email: str = ""
    redmine: dict[str, object] = field(default_factory=dict, repr=False)
    youtrack: dict[str, object] = field(default_factory=dict, repr=False)
```

The example profile must have `is_enable: false`, empty credentials, and no usable token:

```json
{
  "users": [
    {
      "name": "CHANGE_ME",
      "is_enable": false,
      "git_email": "",
      "redmine": {"api_key": "", "user_id": 1, "activity_id": 1, "comment": "development"},
      "youtrack": {"access_token": "", "issue_id": "PROJECT-1"}
    }
  ]
}
```

- [ ] **Step 4: Extend tests for selection and redaction**

Add tests that no enabled users raises `ProfileConfigError`, multiple enabled users without a name raises, selecting a disabled name raises, and `repr(profile)` does not contain either fake token.

- [ ] **Step 5: Run focused tests and commit**

Run: `pytest tests/test_mcp_config.py -q`  
Expected: PASS. Commit as `feat: load MCP users from ignored JSON`.

## Task 2: Bootstrap MCP stdio and expose enabled users

**Files:**
- Create: `mcp_server/app.py`
- Create: `mcp_server/__main__.py`
- Create: `mcp_server/user_tools.py`
- Create: `.opencode/opencode.json`
- Create: `pytest.ini`
- Create: `tests/test_mcp_server.py`
- Modify: `requirements.txt`

**Interfaces:**
- `create_server(users_path: Path | None = None) -> MCPServer` creates one `MCPServer`, registers only explicit tools, and does not load user secrets into tool results.
- `list_enabled_users() -> list[dict[str, str]]` returns names and configured tracker kinds only.
- `python -m mcp_server` runs `server.run(transport="stdio")` under a `__main__` guard.

- [ ] **Step 1: Add failing in-memory MCP contract tests**

Use the SDK's in-memory `Client(server)` and `asyncio.run` (do not add a pytest async plugin). Assert the `list_enabled_users` result contains only enabled names and no fake API token. Assert there are no prompts or resources.

- [ ] **Step 2: Run the test and confirm the missing-module failure**

Run: `pytest tests/test_mcp_server.py -q`  
Expected: FAIL because the MCP package/server modules are not installed or created.

- [ ] **Step 3: Add the SDK and implement the server shell**

Add `mcp>=2.3,<3` to `requirements.txt`. Register `list_enabled_users` on `MCPServer("Work Assistant")`. Load profiles inside the tool call so a missing config yields a safe tool error rather than printing secrets during process startup. Use logging on stderr; do not print to stdout.

Add `pytest.ini` with `addopts = -p no:anyio`: this project uses `asyncio.run` for in-memory MCP tests and does not use AnyIO's pytest plugin; avoiding its auto-load prevents a third-party `CallSpec2` deprecation warning.

```python
from mcp.server import MCPServer


def create_server(users_path: Path | None = None) -> MCPServer:
    server = MCPServer("Work Assistant")
    resolved_path = users_path or default_users_path()
    register_user_tools(server, resolved_path)
    return server
```

Use this project-local config shape; keep it free of server instructions, prompts, and resources:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "work-assistant": {
        "type": "local",
        "command": ["python3", "-m", "mcp_server"],
        "cwd": ".",
        "codemode": false,
        "protocol": "legacy"
      }
    }
  }
}
```

After adding the dependency, run `pip install -r requirements.txt` before running the SDK-backed tests.

- [ ] **Step 4: Verify only the expected MCP catalog is exposed**

Add in-memory assertions for exact tool names at this stage, empty prompt/resource lists, and a safe error for a missing config. Use `Client(server, raise_exceptions=True)` in tests.

- [ ] **Step 5: Run focused tests and commit**

Run: `pytest tests/test_mcp_server.py tests/test_mcp_config.py -q`  
Expected: PASS. Commit as `feat: bootstrap local Work Assistant MCP server`.

## Task 3: Add tracker and git read-only tools

**Files:**
- Create: `mcp_server/tracker_access.py`
- Create: `mcp_server/read_tools.py`
- Create: `tests/test_mcp_read_tools.py`
- Modify: `mcp_server/app.py`

**Interfaces:**
- `build_user_tracker(profile: UserProfile, kind: str, *, issue_id: int | None = None, for_write: bool = False) -> BaseTracker` clones profile config, injects a request-scoped Redmine issue only when supplied, and raises a sanitized `ProfileConfigError` if credentials are incomplete.
- `required_redmine_comment(profile: UserProfile) -> str` returns a non-empty per-user comment or raises a sanitized config error.
- `get_worklogs(user_name: str, tracker: str, start: str, end: str) -> list[dict[str, object]]` returns worklog metadata without credentials.
- `get_git_commits(user_name: str, repo_path: str, start: str, end: str) -> list[dict[str, str]]` uses the profile's `git_email` and existing `GitClient`.

- [ ] **Step 1: Add failing read-only tool tests**

Test Redmine worklog mapping with API key/user/activity and no saved issue ID, YouTrack worklog mapping with the JSON token, and Git commit output from a temporary repo. Assert tool results contain no fake token. Do not change the existing `RedmineTracker.fields` because the GUI remains in use during this phase.

- [ ] **Step 2: Run focused tests and confirm they fail**

Run: `pytest tests/test_mcp_read_tools.py -q`  
Expected: new MCP tests fail because the read tools are not registered.

- [ ] **Step 3: Implement safe tracker construction and read tools**

In `tracker_access.py`, validate Redmine read credentials (`api_key`, `user_id`, `activity_id`) directly and call the adapter's read method without using `is_configured()`; the adapter's `get_worklogs` does not need an issue ID. For writes, require and inject the request-scoped issue ID so the existing tracker remains compatible with the GUI. `required_redmine_comment` rejects a missing/blank comment rather than silently changing the user's configured text. Add date parsing and `start <= end` validation. Construct `GitClient(repo_path)` only after confirming the profile is enabled and has a git email.

```python
def register_read_tools(server: MCPServer, users_path: Path) -> None:
    @server.tool()
    def get_git_commits(
        user_name: str, repo_path: str, start: str, end: str
    ) -> list[dict[str, str]]:
        profile = select_user(load_users(users_path), user_name)
        commits = GitClient(repo_path).list_commits(
            profile.git_email, date.fromisoformat(start), date.fromisoformat(end)
        )
        return [
            {
                "hash": commit.hash,
                "date": commit.date,
                "subject": commit.subject,
                "body": commit.body,
            }
            for commit in commits
        ]
```

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_mcp_read_tools.py tests/test_git_client.py -q`  
Expected: PASS. Commit as `feat: add read-only MCP tracker and git tools`.

## Task 4: Add immutable plans and fail-closed elicitation writes

**Files:**
- Create: `mcp_server/plans.py`
- Create: `mcp_server/write_tools.py`
- Create: `mcp_server/writer.py`
- Create: `tests/test_mcp_write_tools.py`
- Modify: `mcp_server/app.py`

**Interfaces:**
- `PlannedEntry(date: str, hours: float, comment: str, commit_hashes: tuple)` contains only data shown to the user; the tuple stores zero or more validated commit hashes.
- `WritePlan(plan_id: str, user_name: str, destination_kind: str, issue_id: str, entries: tuple, warnings: tuple, target_fingerprint: str, created_at: float)` contains no credentials; the target fingerprint is an internal SHA-256 digest of canonical target-profile JSON and is never returned or logged. Redmine integer issue IDs are stored as decimal strings; YouTrack IDs remain strings.
- `PlanStore.create(user_name, destination_kind, issue_id, entries, warnings, target_fingerprint) -> WritePlan` creates a random ID and rejects multiple entries for the same date; `PlanStore.claim(plan_id) -> WritePlan` rejects unknown, expired, or already claimed plans; `PlanStore.validate_fresh(plan) -> None` rechecks expiry after elicitation.
- `fingerprint_target_config(profile: UserProfile, destination_kind: str) -> str` computes the target profile digest used at prepare and write time.
- `write_plan(plan_id: str, ctx: Context) -> dict[str, object]` is the only MCP tool that reaches `create_worklogs`.
- `execute_plan(plan: WritePlan, users_path: Path) -> dict[str, object]` reloads the enabled profile, verifies its target fingerprint, injects `plan.issue_id` for Redmine or validates the configured YouTrack issue, then calls `create_worklogs` and returns per-entry outcomes.
- `register_write_tool(server, store, execute)` injects the writer callback so the tool can be tested without network access.

- [ ] **Step 1: Add failing plan-store and write-gate tests**

Test unknown, expired, and replayed plan IDs with an injected clock; reject multiple entries for the same date. Add in-memory MCP tests using an executor spy: an accepted `approved=True` elicitation calls the executor once; declined, canceled, false, and unsupported elicitation call it zero times. Test that a target-profile change after preparation is rejected before invoking the writer.

```python
def test_plan_store_claims_once():
    store = PlanStore()
    entry = PlannedEntry("2026-10-28", 1.0, "development", ())
    plan = store.create("Oleg", "redmine", "123", (entry,), ())

    assert store.claim(plan.plan_id) == plan
    with pytest.raises(PlanError):
        store.claim(plan.plan_id)
```

- [ ] **Step 2: Run tests and confirm the missing-plan failure**

Run: `pytest tests/test_mcp_write_tools.py -q`  
Expected: FAIL because plan storage and the write tool do not exist.

- [ ] **Step 3: Implement plan storage and approval**

Use `secrets.token_urlsafe(24)` and a monotonic clock. Claim/remove the plan before elicitation, preventing concurrent or replayed writes. Use the MCP SDK v2 `Context` and a flat Pydantic form; serialize the exact user, issue and entry data in compact JSON inside the elicitation message so newlines, pipes, or quotes in user-controlled comments cannot spoof displayed rows. Catch elicitation failures separately and return a blocked result without calling the writer. Compute `target_fingerprint` as SHA-256 of canonical sorted JSON for only the destination tracker block; keep it out of repr, tool results, logs, and elicitation. Recompute it from the freshly loaded profile in `execute_plan` and compare before any tracker call. Reject duplicate dates when creating a plan because tracker clients report errors by date and per-entry results require unique dates.

```python
class Approval(BaseModel):
    approved: bool = Field(description="Разрешить запись показанных строк")


def register_write_tool(server, store, execute):
    @server.tool()
    async def write_plan(plan_id: str, ctx: Context) -> dict[str, object]:
        plan = store.claim(plan_id)
        try:
            result = await ctx.elicit(format_plan(plan), schema=Approval)
        except Exception:
            return {"status": "blocked", "written": 0, "reason": "Нет подтверждения MCP-клиента"}
        if result.action != "accept" or not result.data.approved:
            return {"status": "declined", "written": 0}
        store.validate_fresh(plan)
        return execute(plan)
```

Use the configured legacy protocol because SDK v2 server-initiated `ctx.elicit` is supported on legacy MCP connections. `register_write_tool` receives `execute=lambda plan: execute_plan(plan, users_path)` in the app and a spy in tests. In tests use an async callback with this behavior:

```python
async def approve(_context, _params):
    return ElicitResult(action="accept", content={"approved": True})
```

Test a second callback returning `ElicitResult(action="decline")`, and call without a callback to prove the writer is untouched. After an accepted response, call `store.validate_fresh(plan)` before the executor; if the user left the form open past 600 seconds, no write occurs.

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_mcp_write_tools.py -q`  
Expected: PASS. Commit as `feat: require MCP elicitation for worklog writes`.

## Task 5: Prepare Redmine eight-hour autofill

**Files:**
- Create: `mcp_server/redmine_tools.py`
- Create: `tests/test_mcp_redmine_tools.py`
- Modify: `mcp_server/app.py`

**Interfaces:**
- `prepare_redmine_autofill(user_name: str, date: str, issue_id: int) -> dict[str, object]` is read-only and returns a stored plan ID plus a public row summary.
- It counts every Redmine worklog for that user/date (all issues), sets `hours = max(0, 8 - existing_hours)`, targets only the request issue, and uses that profile's `redmine.comment`.
- `issue_id` must be a positive integer in this tool call; an issue ID in a profile is ignored.

- [ ] **Step 1: Add failing autofill tests**

Test a date with 3 existing hours yields a plan for 5 hours, a filled day yields no writable plan, an invalid/missing issue ID is rejected, and the Redmine fake's `create_worklogs` is never called during preparation.

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `pytest tests/test_mcp_redmine_tools.py -q`  
Expected: FAIL because the prepare tool is not registered.

- [ ] **Step 3: Implement the read/prepare path**

Reject `issue_id <= 0` before any API call. Parse the ISO date; load and select only an enabled profile; build the Redmine read adapter with the request issue ID; sum worklog hours; create one plan entry only when deficit is positive. Do not call any tracker writer from this module.

```python
def register_redmine_tools(server, users_path: Path, plans: PlanStore) -> None:
    @server.tool()
    def prepare_redmine_autofill(
        user_name: str, date: str, issue_id: int
    ) -> dict[str, object]:
        target_date = Date.fromisoformat(date)  # import datetime.date as Date
        profile = select_user(load_users(users_path), user_name)
        tracker = build_user_tracker(
            profile, "redmine", issue_id=issue_id, for_write=False
        )
        existing = sum(
            row.hours for row in tracker.get_worklogs(target_date, target_date)
        )
        hours = max(0.0, round(8.0 - existing, 2))
        if hours == 0:
            return {"status": "already_filled", "existing_hours": existing}
        plan = plans.create(
            profile.name,
            "redmine",
            str(issue_id),
            (PlannedEntry(date, hours, required_redmine_comment(profile)),),
            (),
            fingerprint_target_config(profile, "redmine"),
        )
        return public_plan(plan)
```

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_mcp_redmine_tools.py -q`  
Expected: PASS. Commit as `feat: prepare Redmine daily autofill through MCP`.

## Task 6: Prepare YouTrack-to-Redmine transfer

**Files:**
- Modify: `mcp_server/redmine_tools.py`
- Modify: `tests/test_mcp_redmine_tools.py`

**Interfaces:**
- `prepare_youtrack_transfer(user_name: str, start: str, end: str, issue_id: int) -> dict[str, object]` aggregates source hours by date and produces at most one target row per day.
- Exact duplicate identity is `(user, date, target issue, hours, redmine.comment)`; skip exact duplicates. If the same target issue/date/comment exists with a different amount, return a conflict and do not stage an additional row for that date.
- Missing or invalid request `issue_id` fails before any write.

- [ ] **Step 1: Add failing transfer tests**

Test summing multiple YouTrack items on one day, copying the per-user comment, exact duplicate suppression, conflicting amount suppression, missing issue rejection, and no POST during preparation.

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `pytest tests/test_mcp_redmine_tools.py -q`  
Expected: the new transfer tests fail because only autofill exists.

- [ ] **Step 3: Implement transfer preparation**

Read YouTrack daily totals and Redmine worklogs for the range. Compare only entries for the request issue and configured per-user comment; put exact duplicates and amount conflicts in `warnings`. Store only conflict-free new rows in the plan with `fingerprint_target_config(profile, "redmine")`. If no rows remain, return `status="nothing_to_write"` and do not create a plan.

```python
for source_row in youtrack_rows:
    same_target = [
        row
        for row in redmine_rows
        if row.date == source_row.date
        and row.issue == str(issue_id)
        and row.description == comment
    ]
    exact = any(row.hours == source_row.hours for row in same_target)
    if exact:
        warnings.append(f"{source_row.date}: already transferred")
    elif same_target:
        warnings.append(f"{source_row.date}: conflicting hours on target issue")
    else:
        planned_entries.append(
            PlannedEntry(source_row.date, source_row.hours, comment, ())
        )
```

Create the plan with the accumulated entries and the Redmine target fingerprint. The one-row-per-day aggregation satisfies the plan store's unique-date invariant.

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_mcp_redmine_tools.py tests/test_youtrack_tracker.py tests/test_redmine_tracker.py -q`  
Expected: PASS. Commit as `feat: prepare idempotent YouTrack to Redmine transfers`.

## Task 7: Prepare agent-proposed YouTrack completion from commits

**Files:**
- Create: `mcp_server/youtrack_tools.py`
- Create: `tests/test_mcp_youtrack_tools.py`
- Modify: `mcp_server/app.py`

**Interfaces:**
- `SuggestedDay(date: str, hours: float, comment: str, commit_hashes: list[str])` is the typed MCP argument model supplied by the agent.
- `prepare_youtrack_fill(user_name: str, repo_path: str, start: str, end: str, entries: list[SuggestedDay]) -> dict[str, object]` returns a stored YouTrack plan and does not call AI or write worklogs.
- `youtrack.issue_id` in the selected JSON profile is the destination issue.

- [ ] **Step 1: Add failing YouTrack completion tests**

Test validation rejects an entry without a commit, a hash not found for that profile/date, non-positive or non-half-hour values, a duplicated date, and a proposal greater than that date's remaining hours to 8. Test valid entries make a plan for the configured YouTrack issue and never call `create_worklogs`.

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `pytest tests/test_mcp_youtrack_tools.py -q`  
Expected: FAIL because the prepare tool and typed entry model do not exist.

- [ ] **Step 3: Implement commit-backed plan validation**

Re-read current YouTrack daily totals and Git commits for the selected profile, path, and period. Require every entry date to contain at least one listed commit hash whose author email and commit date match. Ensure current plus proposed hours do not exceed 8 and that each proposed duration is a positive multiple of 0.5. Preserve the agent's non-empty comment verbatim. Create the plan with `fingerprint_target_config(profile, "youtrack")`.

```python
if len({entry.date for entry in entries}) != len(entries):
    raise ValueError("Для одной даты допускается только одна строка")

for entry in entries:
    day_commits = commits_by_date.get(entry.date, {})
    if not entry.commit_hashes or any(h not in day_commits for h in entry.commit_hashes):
        raise ValueError(f"{entry.date}: нет подходящих коммитов")
    existing = existing_hours_by_date.get(entry.date, 0.0)
    proposed = proposed_hours_by_date.get(entry.date, 0.0) + entry.hours
    if entry.hours <= 0 or entry.hours * 2 != round(entry.hours * 2):
        raise ValueError(f"{entry.date}: часы должны быть положительны и кратны 0.5")
    if existing + proposed > 8.0:
        raise ValueError(f"{entry.date}: предложение превышает остаток до 8 часов")
    if not entry.comment.strip():
        raise ValueError(f"{entry.date}: комментарий обязателен")
    proposed_hours_by_date[entry.date] = proposed
```

- [ ] **Step 4: Run focused tests and commit**

Run: `pytest tests/test_mcp_youtrack_tools.py tests/test_git_client.py tests/test_youtrack_tracker.py -q`  
Expected: PASS. Commit as `feat: prepare agent-proposed YouTrack completion`.

## Task 8: Document setup and verify the complete MCP contract

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `tests/test_mcp_server.py`
- Modify: related MCP tests only if integration coverage reveals a gap.

**Interfaces:**
- README documents local setup, `config/users.json`, `.env` tracker URLs, the three scenarios, mandatory Redmine issue IDs, approval form, and the fact that AI runs in the agent.
- Project `AGENTS.md` describes the MCP entry point while GUI removal remains a later step.

- [ ] **Step 1: Add an MCP catalog integration test**

Use the in-memory SDK client to assert the final tool names exactly match `list_enabled_users`, `get_worklogs`, `get_git_commits`, `prepare_redmine_autofill`, `prepare_youtrack_transfer`, `prepare_youtrack_fill`, and `write_plan`. Assert no prompts/resources are available and the server has no custom instructions.

- [ ] **Step 2: Update setup documentation**

Document `pip install -r requirements.txt`, copying `config/users.example.json` to ignored `config/users.json`, filling the tracker URL env vars, and opening the project in OpenCode. Explain that a Redmine issue ID is asked for every Redmine write and that the MCP approval form is mandatory. Do not add actual credentials or invoke live writes.

- [ ] **Step 3: Run full verification**

Run: `pytest -q`  
Expected: all existing backend tests and all new MCP tests pass. Run `git diff --check`; expected: no output.

- [ ] **Step 4: Commit documentation and final integration tests**

Commit as `docs: document Work Assistant MCP setup` (include any final catalog assertions in the same commit only if Task 1-7 already committed their own tests).

## Phase 2 gate

Do not execute `2026-10-28-work-assistant-gui-removal.md` until all Task 1-8 checks pass and the MCP workflows have been verified through a host without performing unapproved live writes.
