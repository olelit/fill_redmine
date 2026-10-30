# YouTrack → Redmine Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an MCP scenario that copies YouTrack worklogs into one Redmine issue, replacing the user's Redmine entries for every transferred date after explicit approval.

**Architecture:** A new `prepare_youtrack_transfer` tool reads YouTrack and Redmine, aggregates YouTrack hours by date, records the exact Redmine time-entry IDs to delete, and stores an immutable plan. The existing `write_plan` gate asks for approval; `execute_plan` then deletes the recorded entries and creates one Redmine entry per date.

**Tech Stack:** Python 3.10+, MCP Python SDK v2, `requests`, existing tracker/client layers, pytest.

## Global Constraints

- Use absolute imports and type hints everywhere.
- Max line length: 100 characters.
- Comments in Redmine are exactly `redmine.comment` from `config/users.json`; never append YouTrack issue IDs.
- The Redmine issue ID is required per transfer call and must never be read from JSON or SQLite.
- Default period is the 1st day of the current month through today.
- Never write or delete anything during `prepare_*`; only `write_plan` may mutate trackers.
- Tests must use in-memory MCP clients and fakes; no live tracker requests.
- Tool output, errors and logs must never contain `api_key`, `access_token` or authorization headers.
- The MCP catalog must contain exactly six tools and no prompts/resources/instructions.
- Run `.venv/bin/pytest -q` before every commit; each task ends with its own commit.

---

### Task 1: Redmine Time-Entry Deletion and Raw Reads

**Files:**
- Modify: `clients/redmine_client.py`
- Modify: `trackers/redmine.py`
- Test: `tests/test_redmine_tracker.py`

**Interfaces:**
- Consumes: existing `RedmineClient.get_time_entries(user_id, start, end)`.
- Produces: `RedmineClient.delete_time_entries(entry_ids: list[int]) -> list[tuple[int, str]]`.
- Produces: `RedmineTracker.get_time_entries(start: date, end: date) -> list[dict]`.
- Produces: `RedmineTracker.delete_time_entries(entry_ids: list[int]) -> list[tuple[int, str]]`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_redmine_tracker.py`:

```python
def test_tracker_exposes_raw_time_entries_with_user_id():
    tracker = RedmineTracker(
        {"api_key": "key", "user_id": 16, "activity_id": 9, "issue_id": 2682}
    )
    raw = [{"id": 901, "spent_on": "2026-10-01", "hours": 8.0}]

    with patch.object(
        RedmineClient, "get_time_entries", return_value=raw
    ) as mock_get:
        entries = tracker.get_time_entries(
            date(2026, 10, 1), date(2026, 10, 2)
        )

    assert entries == raw
    mock_get.assert_called_once_with(
        user_id=16, start=date(2026, 10, 1), end=date(2026, 10, 2)
    )


def test_delete_time_entries_treats_404_as_success():
    deleted = MagicMock()
    deleted.status_code = 204
    deleted.text = ""
    missing = MagicMock()
    missing.status_code = 404
    missing.text = ""

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.requests.delete",
        side_effect=[deleted, missing],
    ) as mock_delete:
        errors = RedmineClient("key").delete_time_entries([901, 902])

    assert errors == []
    assert mock_delete.call_count == 2
    assert mock_delete.call_args_list[0].args[0] == (
        "http://redmine/time_entries/901.json"
    )
    assert mock_delete.call_args_list[0].kwargs["headers"] == {
        "X-Redmine-API-Key": "key"
    }


def test_delete_time_entries_reports_errors_and_continues():
    forbidden = MagicMock()
    forbidden.status_code = 403
    forbidden.text = "denied"
    deleted = MagicMock()
    deleted.status_code = 204
    deleted.text = ""

    with patch(
        "clients.redmine_client.Config.get_redmine_base_url",
        return_value="http://redmine",
    ), patch(
        "clients.redmine_client.requests.delete",
        side_effect=[
            forbidden,
            requests.ConnectionError("boom"),
            deleted,
        ],
    ) as mock_delete:
        errors = RedmineClient("key").delete_time_entries([1, 2, 3])

    assert errors == [(1, "403 denied"), (2, "boom")]
    assert mock_delete.call_count == 3


def test_tracker_deletes_time_entries():
    tracker = RedmineTracker(
        {"api_key": "key", "user_id": 16, "activity_id": 9, "issue_id": 2682}
    )

    with patch.object(
        RedmineClient, "delete_time_entries", return_value=[(2, "boom")]
    ) as mock_delete:
        errors = tracker.delete_time_entries([1, 2])

    assert errors == [(2, "boom")]
    mock_delete.assert_called_once_with([1, 2])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_redmine_tracker.py -v
```

Expected: the four new tests fail because `RedmineTracker.get_time_entries`, `RedmineTracker.delete_time_entries` and `RedmineClient.delete_time_entries` do not exist.

- [ ] **Step 3: Implement the client method**

In `clients/redmine_client.py`, add after `get_time_entries`:

```python
    def delete_time_entries(
        self, entry_ids: list[int]
    ) -> list[tuple[int, str]]:
        url = f"{self.base_url}/time_entries"
        headers = {"X-Redmine-API-Key": self.api_key}
        errors: list[tuple[int, str]] = []
        for entry_id in entry_ids:
            try:
                response = requests.delete(
                    f"{url}/{entry_id}.json",
                    headers=headers,
                    timeout=10,
                )
            except requests.RequestException as exc:
                errors.append((entry_id, str(exc)))
                continue

            if 200 <= response.status_code < 300 or response.status_code == 404:
                continue
            errors.append(
                (entry_id, f"{response.status_code} {response.text[:200]}")
            )
        return errors
```

- [ ] **Step 4: Implement the tracker methods**

In `trackers/redmine.py`, replace `get_worklogs` with:

```python
    def get_time_entries(self, start: date, end: date) -> list[dict]:
        client = RedmineClient(api_key=self.config["api_key"])
        return client.get_time_entries(
            user_id=int(self.config["user_id"]),
            start=start,
            end=end,
        )

    def get_worklogs(self, start: date, end: date) -> list[WorklogDTO]:
        result: list[WorklogDTO] = []
        for entry in self.get_time_entries(start, end):
            issue = entry.get("issue") or {}
            result.append(
                WorklogDTO(
                    date=entry["spent_on"],
                    hours=float(entry.get("hours", 0)),
                    description=entry.get("comments", ""),
                    issue=str(issue.get("id", "")),
                    source=self.kind,
                )
            )
        return result

    def delete_time_entries(
        self, entry_ids: list[int]
    ) -> list[tuple[int, str]]:
        client = RedmineClient(api_key=self.config["api_key"])
        return client.delete_time_entries(entry_ids)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_redmine_tracker.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit**

```bash
git add clients/redmine_client.py trackers/redmine.py tests/test_redmine_tracker.py
git commit -m "feat: add Redmine time entry deletion"
```

---

### Task 2: Plan Deletions, Approval Summary and Overwrite Writer

**Files:**
- Modify: `mcp_server/plans.py`
- Modify: `mcp_server/write_tools.py`
- Modify: `mcp_server/writer.py`
- Test: `tests/test_mcp_write_tools.py`

**Interfaces:**
- Consumes: `RedmineTracker.delete_time_entries(entry_ids)` from Task 1.
- Produces: `PlannedDeletion(date: str, entry_id: int, hours: float)`.
- Produces: `WritePlan.deletions: tuple[PlannedDeletion, ...]`.
- Produces: `PlanStore.create(..., deletions: tuple[PlannedDeletion, ...] = ()) -> WritePlan`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mcp_write_tools.py`:

```python
def _deletion(day="2026-10-20", entry_id=901, hours=1.5):
    return PlannedDeletion(date=day, entry_id=entry_id, hours=hours)


def test_plan_store_accepts_deletions_for_entry_dates():
    store = PlanStore()
    plan = _create_plan(
        store,
        "Oleg",
        "redmine",
        "42",
        (_entry(),),
        (),
        deletions=(_deletion(),),
    )

    assert plan.deletions == (_deletion(),)


def test_plan_store_rejects_deletion_for_unknown_date():
    store = PlanStore()

    with pytest.raises(ValueError, match="entry dates"):
        _create_plan(
            store,
            "Oleg",
            "redmine",
            "42",
            (_entry(),),
            (),
            deletions=(_deletion(day="2026-10-21"),),
        )


def test_writer_redmine_deletes_existing_entries_before_creating(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    config = {
        "api_key": "redmine-secret",
        "user_id": 17,
        "activity_id": 9,
        "comment": "development",
    }
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "redmine": config}],
    )
    store = PlanStore()
    plan = _create_plan(
        store,
        "Oleg",
        "redmine",
        "42",
        (_entry(),),
        (),
        _fingerprint("redmine", config),
        deletions=(_deletion(),),
    )
    calls = []

    class FakeTracker:
        def delete_time_entries(self, entry_ids):
            calls.append(("delete", list(entry_ids)))
            return []

        def create_worklogs(self, records):
            calls.append(
                ("create", [(record.date, record.hours) for record in records])
            )
            return []

    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *args, **kwargs: FakeTracker(),
    )

    result = execute_plan(plan, path)

    assert calls == [
        ("delete", [901]),
        ("create", [("2026-10-20", 1.5)]),
    ]
    assert result == {
        "results": [{"date": "2026-10-20", "issue": "42", "status": "created"}]
    }
    assert "redmine-secret" not in json.dumps(result)


def test_writer_redmine_skips_creation_when_deletion_fails(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    config = {
        "api_key": "redmine-secret",
        "user_id": 17,
        "activity_id": 9,
        "comment": "development",
    }
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "redmine": config}],
    )
    store = PlanStore()
    plan = _create_plan(
        store,
        "Oleg",
        "redmine",
        "42",
        (
            _entry(date="2026-10-20"),
            _entry(date="2026-10-21", issue_id="42"),
        ),
        (),
        _fingerprint("redmine", config),
        deletions=(
            _deletion(day="2026-10-20", entry_id=901),
            _deletion(day="2026-10-21", entry_id=902),
        ),
    )
    written = []

    class FakeTracker:
        def delete_time_entries(self, entry_ids):
            return [(901, "denied")]

        def create_worklogs(self, records):
            written.append([record.date for record in records])
            return []

    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *args, **kwargs: FakeTracker(),
    )

    result = execute_plan(plan, path)

    assert written == [["2026-10-21"]]
    assert result == {
        "results": [
            {"date": "2026-10-20", "issue": "42", "status": "failed"},
            {"date": "2026-10-21", "issue": "42", "status": "created"},
        ]
    }


def test_write_tool_approval_form_shows_deletion_count(tmp_path):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "redmine": {
            "api_key": "redmine-secret",
            "user_id": 17,
            "activity_id": 9,
            "comment": "development",
        }}],
    )
    store = PlanStore()
    plan = _create_plan(
        store,
        "Oleg",
        "redmine",
        "42",
        (_entry(),),
        (),
        deletions=(_deletion(), _deletion(entry_id=902, hours=2.5)),
    )
    messages = []

    async def elicitation_callback(context, params):
        messages.append(params.message)
        return types.ElicitResult(action="decline")

    async def call():
        async with Client(
            create_server(
                path,
                write_store=store,
                write_executor=lambda _plan: {},
            ),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool(
                "write_plan", {"plan_id": plan.plan_id}
            )

    asyncio.run(call())

    assert len(messages) == 1
    assert "Будет удалено: 2 старых записей (4 ч)" in messages[0]
    assert "redmine-secret" not in messages[0]
```

Also update the existing helper:

```python
def _create_plan(
    store,
    user_name,
    kind,
    issue_id,
    entries,
    warnings,
    fingerprint="test",
    deletions=(),
):
    return store.create(
        user_name,
        kind,
        issue_id,
        entries,
        warnings,
        fingerprint,
        deletions=deletions,
    )
```

And add the import:

```python
from mcp_server.plans import (
    PLAN_TTL_SECONDS,
    PlanError,
    PlanStore,
    PlannedDeletion,
    PlannedEntry,
    fingerprint_target_config,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_mcp_write_tools.py -v
```

Expected: import fails because `PlannedDeletion` does not exist; the new tests cannot run.

- [ ] **Step 3: Add `PlannedDeletion` and plan deletion storage**

In `mcp_server/plans.py`, add after `PlanError`:

```python
@dataclass(frozen=True)
class PlannedDeletion:
    date: str
    entry_id: int
    hours: float
```

Change `WritePlan` to add the field at the end:

```python
    target_fingerprint: str = field(repr=False)
    created_at: float
    deletions: tuple[PlannedDeletion, ...] = ()
```

In `WritePlan.__post_init__` add:

```python
        object.__setattr__(self, "deletions", tuple(self.deletions))
```

Change `PlanStore.create` signature to:

```python
    def create(
        self,
        user_name: str,
        destination_kind: str,
        issue_id: str,
        entries: tuple[PlannedEntry, ...],
        warnings: tuple[str, ...],
        target_fingerprint: str,
        deletions: tuple[PlannedDeletion, ...] = (),
    ) -> WritePlan:
```

At the start of the method add:

```python
        deletions = tuple(deletions)
```

After the duplicate-entries check add:

```python
        entry_dates = {entry.date for entry in entries}
        if any(deletion.date not in entry_dates for deletion in deletions):
            raise ValueError("Plan deletions must reference entry dates")
        if len({deletion.entry_id for deletion in deletions}) != len(deletions):
            raise ValueError("Plan deletions must have unique entry IDs")
```

Pass the field to the constructor:

```python
            deletions=deletions,
```

- [ ] **Step 4: Add the deletion line to the approval message**

In `mcp_server/write_tools.py`, replace the `lines` construction in `_approval_message` with:

```python
    lines = [
        f"Записать {len(plan.entries)} worklog'ов на {total:g} ч?",
        f"Пользователь: {plan.user_name}",
        f"Трекер: {tracker}",
        f"Период: {period}",
    ]
    if plan.deletions:
        deleted_hours = sum(deletion.hours for deletion in plan.deletions)
        lines.append(
            f"Будет удалено: {len(plan.deletions)} старых записей "
            f"({deleted_hours:g} ч)"
        )
    lines.extend(
        [
            f"Предупреждений: {len(plan.warnings)}",
            "Подробный план выведен в чате.",
        ]
    )
    return "\n".join(lines)
```

- [ ] **Step 5: Implement delete-then-create in the Redmine writer**

In `mcp_server/writer.py`, replace `_execute_redmine` with:

```python
def _execute_redmine(plan: WritePlan, profile: UserProfile) -> dict[str, object]:
    tracker = build_user_tracker(
        profile,
        "redmine",
        issue_id=_redmine_issue_id(plan.issue_id),
        for_write=True,
    )
    failed_dates: set[str] = set()
    if plan.deletions:
        deletion_errors = tracker.delete_time_entries(
            [deletion.entry_id for deletion in plan.deletions]
        )
        failed_ids = {
            entry_id for entry_id, _message in deletion_errors
        }
        failed_dates.update(
            deletion.date
            for deletion in plan.deletions
            if deletion.entry_id in failed_ids
        )

    records = [
        _record(plan, entry, plan.issue_id)
        for entry in plan.entries
        if entry.date not in failed_dates
    ]
    if records:
        failures = tracker.create_worklogs(records)
        failed_dates.update(
            entry_date for entry_date, _message in failures
        )

    return {
        "results": [
            {
                "date": entry.date,
                "issue": plan.issue_id,
                "status": "failed" if entry.date in failed_dates else "created",
            }
            for entry in plan.entries
        ]
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_mcp_write_tools.py -v
```

Expected: all tests in the file pass.

- [ ] **Step 7: Commit**

```bash
git add mcp_server/plans.py mcp_server/write_tools.py mcp_server/writer.py tests/test_mcp_write_tools.py
git commit -m "feat: support Redmine worklog replacement plans"
```

---

### Task 3: Period Helper and `prepare_youtrack_transfer` Tool

**Files:**
- Create: `mcp_server/periods.py`
- Modify: `mcp_server/youtrack_tools.py`
- Create: `mcp_server/transfer_tools.py`
- Modify: `mcp_server/app.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `tests/test_mcp_read_tools.py`
- Create: `tests/test_mcp_transfer_tools.py`

**Interfaces:**
- Consumes: `RedmineTracker.get_time_entries` from Task 1.
- Consumes: `PlannedDeletion` and `PlanStore.create(..., deletions=...)` from Task 2.
- Produces: `parse_period(start: str | None, end: str | None) -> tuple[date, date]`.
- Produces: `prepare_youtrack_transfer(user_name: str, issue_id: int, start: str | None = None, end: str | None = None) -> dict[str, object]`.

- [ ] **Step 1: Write the failing MCP contract tests**

Create `tests/test_mcp_transfer_tools.py`:

```python
import asyncio
import json
from datetime import date
from pathlib import Path

from mcp.client import Client

from dto.worklog_dto import WorklogDTO
from mcp_server.app import create_server
from mcp_server.plans import PlanStore

SECRET_YOUTRACK = "youtrack-secret"
SECRET_REDMINE = "redmine-secret"


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def _user(**overrides: object) -> dict[str, object]:
    redmine: dict[str, object] = {
        "api_key": SECRET_REDMINE,
        "user_id": 16,
        "activity_id": 9,
        "comment": "development",
    }
    youtrack: dict[str, object] = {
        "access_token": SECRET_YOUTRACK,
        "issue_id": "DRIVEO-5062",
    }
    redmine.update(overrides.pop("redmine", {}))
    youtrack.update(overrides.pop("youtrack", {}))
    profile: dict[str, object] = {
        "name": "Oleg",
        "is_enable": True,
        "git_email": "oleg@example.com",
        "redmine": redmine,
        "youtrack": youtrack,
    }
    profile.update(overrides)
    return profile


def _install_fakes(monkeypatch, worklogs=(), redmine_entries=()):
    writes: list[object] = []
    deletes: list[object] = []

    class FakeTracker:
        def __init__(self, kind: str):
            self.kind = kind

        def get_worklogs(self, start, end):
            if self.kind == "youtrack":
                return list(worklogs)
            return []

        def get_time_entries(self, start, end):
            return list(redmine_entries)

        def create_worklogs(self, records):
            writes.append(list(records))
            return []

        def delete_time_entries(self, entry_ids):
            deletes.append(list(entry_ids))
            return []

    monkeypatch.setattr(
        "mcp_server.transfer_tools.build_user_tracker",
        lambda profile, kind, **kwargs: FakeTracker(kind),
    )
    return writes, deletes


def _call(
    path: Path,
    store: PlanStore,
    issue_id: int = 12345,
    start: str | None = "2026-10-20",
    end: str | None = "2026-10-21",
):
    arguments: dict[str, object] = {
        "user_name": "Oleg",
        "issue_id": issue_id,
    }
    if start is not None:
        arguments["start"] = start
    if end is not None:
        arguments["end"] = end

    async def call():
        async with Client(create_server(path, write_store=store)) as client:
            return await client.call_tool(
                "prepare_youtrack_transfer", arguments
            )

    return asyncio.run(call())


def _ok(result) -> dict[str, object]:
    assert result.is_error is False, str(result.content)
    return json.loads(result.content[0].text)


def _error(result) -> str:
    assert result.is_error is True, str(result.content)
    return str(result.content)


def test_prepare_aggregates_worklogs_and_plans_replacement(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    worklogs = [
        WorklogDTO(date="2026-10-20", hours=7.0, issue="DRIVEO-5062"),
        WorklogDTO(date="2026-10-20", hours=1.0, issue="DRIVEO-2542"),
        WorklogDTO(date="2026-10-21", hours=4.0, issue="DRIVEO-5183"),
    ]
    redmine_entries = [
        {
            "id": 901,
            "spent_on": "2026-10-20",
            "hours": 8.0,
            "issue": {"id": 111},
        },
        {
            "id": 902,
            "spent_on": "2026-10-22",
            "hours": 2.0,
            "issue": {"id": 222},
        },
    ]
    writes, deletes = _install_fakes(
        monkeypatch, worklogs, redmine_entries
    )
    store = PlanStore()

    data = _ok(_call(path, store))

    assert data["status"] == "plan_created"
    assert data["user"] == "Oleg"
    assert data["destination"] == {"tracker": "redmine", "issue": 12345}
    assert data["period"] == {
        "start": "2026-10-20",
        "end": "2026-10-21",
    }
    assert data["entries"] == [
        {
            "date": "2026-10-20",
            "issue": 12345,
            "hours": 8.0,
            "comment": "development",
            "source_issues": ["DRIVEO-2542", "DRIVEO-5062"],
            "replaces": [{"id": 901, "hours": 8.0}],
        },
        {
            "date": "2026-10-21",
            "issue": 12345,
            "hours": 4.0,
            "comment": "development",
            "source_issues": ["DRIVEO-5183"],
            "replaces": [],
        },
    ]
    assert data["warnings"] == []
    assert SECRET_YOUTRACK not in json.dumps(data)
    assert SECRET_REDMINE not in json.dumps(data)
    assert writes == []
    assert deletes == []

    plan = store.claim(data["plan_id"])
    assert plan.destination_kind == "redmine"
    assert plan.issue_id == "12345"
    assert [
        (deletion.date, deletion.entry_id, deletion.hours)
        for deletion in plan.deletions
    ] == [("2026-10-20", 901, 8.0)]


def test_prepare_uses_current_month_when_period_is_omitted(
    tmp_path, monkeypatch
):
    today = date.today()
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            WorklogDTO(
                date=today.isoformat(),
                hours=2.0,
                issue="DRIVEO-1",
            )
        ],
    )
    store = PlanStore()

    data = _ok(_call(path, store, start=None, end=None))

    assert data["period"] == {
        "start": f"{today.year:04d}-{today.month:02d}-01",
        "end": today.isoformat(),
    }


def test_prepare_warns_when_daily_hours_exceed_eight(
    tmp_path, monkeypatch
):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [
            WorklogDTO(date="2026-10-20", hours=7.0, issue="DRIVEO-1"),
            WorklogDTO(date="2026-10-20", hours=3.0, issue="DRIVEO-2"),
        ],
    )
    store = PlanStore()

    data = _ok(_call(path, store))

    assert data["entries"][0]["hours"] == 10.0
    assert data["warnings"] == [
        "2026-10-20: YouTrack hours 10 exceed 8"
    ]


def test_prepare_rejects_no_source_worklogs(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(monkeypatch, [])

    error = _error(_call(path, PlanStore()))

    assert "no youtrack worklogs" in error.lower()
    assert SECRET_YOUTRACK not in error


def test_prepare_rejects_missing_redmine_comment(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user(redmine={"comment": "   "})])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(_call(path, PlanStore()))

    assert "redmine comment is required" in error.lower()
    assert SECRET_REDMINE not in error


def test_prepare_rejects_invalid_issue_id(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(_call(path, PlanStore(), issue_id=0))

    assert "positive integer" in error.lower()


def test_prepare_rejects_invalid_period(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
    )

    error = _error(
        _call(
            path,
            PlanStore(),
            start="2026-10-21",
            end="2026-10-20",
        )
    )

    assert "start date must not be after end date" in error.lower()


def test_prepare_rejects_redmine_entry_without_id(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [_user()])
    _install_fakes(
        monkeypatch,
        [WorklogDTO(date="2026-10-20", hours=2.0, issue="DRIVEO-1")],
        [{"spent_on": "2026-10-20", "hours": 8.0}],
    )

    error = _error(_call(path, PlanStore()))

    assert "redmine time entry id is missing" in error.lower()
```

Update `tests/test_mcp_server.py` expected catalog:

```python
    assert [tool.name for tool in tools.tools] == [
        "list_enabled_users",
        "get_worklogs",
        "get_git_commits",
        "prepare_youtrack_fill",
        "prepare_youtrack_transfer",
        "write_plan",
    ]
```

Update `tests/test_mcp_read_tools.py` expected catalog:

```python
    assert [tool.name for tool in tools.tools] == [
        "list_enabled_users",
        "get_worklogs",
        "get_git_commits",
        "prepare_youtrack_fill",
        "prepare_youtrack_transfer",
        "write_plan",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_mcp_transfer_tools.py tests/test_mcp_server.py tests/test_mcp_read_tools.py -v
```

Expected: `prepare_youtrack_transfer` is unknown; the contract test fails before assertions.

- [ ] **Step 3: Create the shared period helper**

Create `mcp_server/periods.py`:

```python
from datetime import date


class PeriodError(ValueError):
    """Raised when a requested period is invalid."""


def default_period(today: date) -> tuple[date, date]:
    return today.replace(day=1), today


def parse_period(
    start: str | None, end: str | None, today: date | None = None
) -> tuple[date, date]:
    current = date.today() if today is None else today
    default_start, default_end = default_period(current)
    start_date = _parse_date(start) if start is not None else default_start
    end_date = _parse_date(end) if end is not None else default_end
    if start_date > end_date:
        raise PeriodError("Start date must not be after end date")
    return start_date, end_date


def _parse_date(raw: str) -> date:
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise PeriodError(
            "Dates must use YYYY-MM-DD ISO format"
        ) from None
    if value.isoformat() != raw:
        raise PeriodError("Dates must use YYYY-MM-DD ISO format")
    return value
```

- [ ] **Step 4: Reuse the helper in YouTrack tools**

In `mcp_server/youtrack_tools.py`, add the import:

```python
from mcp_server.periods import default_period as _default_period
from mcp_server.periods import parse_period as _period
```

Delete the local `_default_period`, `_period` and `_period_date` functions at the bottom of the file. Keep the existing `_period` call site unchanged.

- [ ] **Step 5: Implement the transfer tool**

Create `mcp_server/transfer_tools.py`:

```python
import math
from datetime import date
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_server.config import ProfileConfigError, load_users, select_user
from mcp_server.periods import PeriodError, parse_period
from mcp_server.plans import (
    PlanStore,
    PlannedDeletion,
    PlannedEntry,
    fingerprint_target_config,
)
from mcp_server.tracker_access import (
    build_user_tracker,
    required_redmine_comment,
)
from trackers.base import BaseTracker

MAX_DAILY_HOURS = 8.0
HOURS_TOLERANCE = 1e-9


class RedmineTransferError(Exception):
    """Raised when a YouTrack to Redmine transfer cannot be planned."""


def register_transfer_tools(
    server: MCPServer, users_path: Path, plans: PlanStore
) -> None:
    def prepare_youtrack_transfer(
        user_name: str,
        issue_id: int,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, object]:
        try:
            return _prepare_youtrack_transfer(
                users_path, plans, user_name, issue_id, start, end
            )
        except (
            ProfileConfigError,
            PeriodError,
            RedmineTransferError,
            ValueError,
        ) as exc:
            raise ToolError(str(exc)) from None

    server.add_tool(
        prepare_youtrack_transfer, name="prepare_youtrack_transfer"
    )


def _prepare_youtrack_transfer(
    users_path: Path,
    plans: PlanStore,
    user_name: str,
    issue_id: int,
    start: str | None,
    end: str | None,
) -> dict[str, object]:
    target_issue = _target_issue(issue_id)
    start_date, end_date = parse_period(start, end)
    profile = select_user(load_users(users_path), user_name)
    comment = required_redmine_comment(profile)
    source = build_user_tracker(profile, "youtrack")
    destination = build_user_tracker(profile, "redmine")
    worklogs = source.get_worklogs(start_date, end_date)
    if not worklogs:
        raise RedmineTransferError(
            "No YouTrack worklogs found for the requested period"
        )

    totals, source_issues = _aggregate(worklogs)
    existing_by_date = _entries_by_date(
        _redmine_entries(destination, start_date, end_date)
    )
    entries: list[PlannedEntry] = []
    deletions: list[PlannedDeletion] = []
    warnings: list[str] = []
    for day in sorted(totals):
        hours = totals[day]
        if hours > MAX_DAILY_HOURS + HOURS_TOLERANCE:
            warnings.append(
                f"{day}: YouTrack hours {hours:g} exceed "
                f"{MAX_DAILY_HOURS:g}"
            )
        entries.append(
            PlannedEntry(
                date=day,
                hours=hours,
                comment=comment,
                commit_hashes=(),
                issue_id=str(target_issue),
            )
        )
        for raw_entry in existing_by_date.get(day, []):
            deletions.append(_deletion(day, raw_entry))

    plan = plans.create(
        user_name=profile.name,
        destination_kind="redmine",
        issue_id=str(target_issue),
        entries=tuple(entries),
        warnings=tuple(warnings),
        target_fingerprint=fingerprint_target_config(profile, "redmine"),
        deletions=tuple(deletions),
    )
    return {
        "status": "plan_created",
        "plan_id": plan.plan_id,
        "user": plan.user_name,
        "destination": {"tracker": "redmine", "issue": target_issue},
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "entries": [
            {
                "date": entry.date,
                "issue": target_issue,
                "hours": entry.hours,
                "comment": entry.comment,
                "source_issues": sorted(
                    source_issues.get(entry.date, set())
                ),
                "replaces": [
                    {"id": deletion.entry_id, "hours": deletion.hours}
                    for deletion in plan.deletions
                    if deletion.date == entry.date
                ],
            }
            for entry in plan.entries
        ],
        "warnings": list(plan.warnings),
    }


def _target_issue(raw: int) -> int:
    if isinstance(raw, bool):
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        )
    try:
        issue = int(raw)
    except (TypeError, ValueError):
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        ) from None
    if issue <= 0:
        raise RedmineTransferError(
            "Redmine issue ID must be a positive integer"
        )
    return issue


def _aggregate(
    worklogs: list,
) -> tuple[dict[str, float], dict[str, set[str]]]:
    totals: dict[str, float] = {}
    issues: dict[str, set[str]] = {}
    for item in worklogs:
        day = item.date
        if not isinstance(day, str) or not day:
            raise RedmineTransferError("YouTrack worklog has no date")
        try:
            hours = float(item.hours)
        except (TypeError, ValueError):
            raise RedmineTransferError(
                f"{day}: invalid YouTrack hours"
            ) from None
        if not math.isfinite(hours) or hours <= 0:
            raise RedmineTransferError(f"{day}: invalid YouTrack hours")
        totals[day] = round(totals.get(day, 0.0) + hours, 2)
        issue = item.issue.strip() if isinstance(item.issue, str) else ""
        if issue:
            issues.setdefault(day, set()).add(issue)
    return totals, issues


def _redmine_entries(
    tracker: BaseTracker, start_date: date, end_date: date
) -> list[dict]:
    getter = getattr(tracker, "get_time_entries", None)
    if getter is None:
        raise RedmineTransferError(
            "Redmine tracker cannot read time entry IDs"
        )
    return getter(start_date, end_date)


def _entries_by_date(entries: list[dict]) -> dict[str, list[dict]]:
    by_date: dict[str, list[dict]] = {}
    for entry in entries:
        day = entry.get("spent_on")
        if not isinstance(day, str) or not day:
            raise RedmineTransferError(
                "Redmine time entry has no spent_on date"
            )
        by_date.setdefault(day, []).append(entry)
    return by_date


def _deletion(day: str, entry: dict) -> PlannedDeletion:
    entry_id = entry.get("id")
    if (
        isinstance(entry_id, bool)
        or not isinstance(entry_id, int)
        or entry_id <= 0
    ):
        raise RedmineTransferError(
            f"{day}: Redmine time entry ID is missing"
        )
    try:
        hours = float(entry.get("hours", 0))
    except (TypeError, ValueError):
        raise RedmineTransferError(
            f"{day}: invalid Redmine hours"
        ) from None
    if not math.isfinite(hours) or hours < 0:
        raise RedmineTransferError(f"{day}: invalid Redmine hours")
    return PlannedDeletion(date=day, entry_id=entry_id, hours=hours)
```

- [ ] **Step 6: Register the new tool**

In `mcp_server/app.py`, add the import:

```python
from mcp_server.transfer_tools import register_transfer_tools
```

Register it after `register_youtrack_tools` and before the write tool:

```python
    register_transfer_tools(server, resolved_users_path, store)
```

- [ ] **Step 7: Run tests to verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_mcp_transfer_tools.py tests/test_mcp_server.py tests/test_mcp_read_tools.py tests/test_mcp_youtrack_tools.py -v
```

Expected: all selected tests pass; the YouTrack suite still passes after the period refactor.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/periods.py mcp_server/youtrack_tools.py mcp_server/transfer_tools.py mcp_server/app.py tests/test_mcp_transfer_tools.py tests/test_mcp_server.py tests/test_mcp_read_tools.py
git commit -m "feat: add YouTrack to Redmine transfer tool"
```

---

### Task 4: Documentation and Full Verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Possibly modify: `tests/test_mcp_server.py` only if the catalog changed unexpectedly.

**Interfaces:**
- Consumes: all tools and behaviors from Tasks 1–3.
- Produces: user/contributor documentation for the new transfer scenario.

- [ ] **Step 1: Update README**

In `README.md`:

1. Rename the section heading `## MCP-сервер (YouTrack fill)` to `## MCP-сервер (worklogs)`.
2. In the install block, change the env comment to:

```bash
cp .env.example .env                 # нужны YOUTRACK_BASE_URL и REDMINE_BASE_URL
```

3. Extend the profile list with Redmine fields:

```markdown
- `redmine.api_key` — API-ключ Redmine;
- `redmine.user_id` — ID пользователя Redmine;
- `redmine.activity_id` — ID activity для time entry;
- `redmine.comment` — обязательный комментарий, например `development`;
```

4. Replace the sentence `AI-ключи серверу не нужны: он не вызывает модели. Redmine-сценарии в этой фазе не реализованы (Redmine остаётся только в GUI).` with:

```markdown
AI-ключи серверу не нужны: он не вызывает модели. Redmine используется для
чтения и перезаписи time entries, YouTrack — как источник worklog'ов.
```

5. Replace `Сервер отдаёт ровно пять tools, без prompts и resources:` with `Сервер отдаёт ровно шесть tools, без prompts и resources:` and add a table row after `prepare_youtrack_fill`:

```markdown
| `prepare_youtrack_transfer` | собрать план переноса YouTrack → Redmine |
```

6. After the existing YouTrack fill paragraphs, add:

```markdown
### Перенос YouTrack → Redmine

`prepare_youtrack_transfer(user_name, issue_id, start, end)` читает worklog'и
YouTrack, суммирует часы по датам и готовит одну запись Redmine на дату в
указанный `issue_id`. `issue_id` обязателен в каждом вызове и не берётся из
JSON. Период по умолчанию — с 1-го числа текущего месяца по сегодня.

Комментарий всегда равен `redmine.comment` (например, `development`); задачи
YouTrack в комментарий не попадают. Если за дату уже есть Redmine-записи этого
пользователя, все они будут удалены после подтверждения и заменены одной новой
записью. Даты без worklog'ов YouTrack не трогаются. Форма `write_plan`
показывает количество и часы удаляемых записей.
```

- [ ] **Step 2: Update AGENTS.md**

In `AGENTS.md`:

1. Replace `It exposes exactly five tools and no prompts/resources:` with `It exposes exactly six tools and no prompts/resources:`.
2. Add after the `prepare_youtrack_fill` bullet:

```markdown
- `prepare_youtrack_transfer` — builds a YouTrack → Redmine transfer plan,
  never writes;
```

3. Add a transfer rules block before `Security rules:`:

```markdown
YouTrack → Redmine transfer rules:

- `prepare_youtrack_transfer` accepts a required positive Redmine `issue_id`;
  the ID is never read from JSON or SQLite.
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
```

4. Remove the line `- Redmine MCP scenarios are not implemented in this phase; Redmine remains GUI-only. The server needs no AI keys.` and rely on the new rules; keep `The server needs no AI keys.` by adding it to the end of the new block.
5. Change `- REDMINE_BASE_URL — Redmine instance URL (GUI only)` to `- REDMINE_BASE_URL — Redmine instance URL (GUI and MCP server)`.
6. Change the final catalog note to `The MCP catalog is asserted in tests/test_mcp_server.py (six tools, no prompts/resources/instructions).`

- [ ] **Step 3: Run the full suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass, including the existing 308 tests plus the new ones.

- [ ] **Step 4: Check the diff**

Run:

```bash
git diff --check
git diff --stat
```

Expected: no whitespace errors; only README, AGENTS and the intended source/test files are listed across the task commits.

- [ ] **Step 5: Commit**

```bash
git add README.md AGENTS.md
git commit -m "docs: document YouTrack to Redmine transfer"
```

---

### Task 5: Live October Transfer (after user supplies the Redmine issue ID)

**Files:**
- No code changes.

**Interfaces:**
- Consumes: `prepare_youtrack_transfer` and `write_plan` from Task 3.
- Produces: October 2026 YouTrack worklogs written to the user's Redmine issue.

- [ ] **Step 1: Ask the user for the Redmine issue ID**

Ask exactly one question: which Redmine issue ID should receive the transfer.
Do not guess and do not read it from `config/users.json`, SQLite or Git history.

- [ ] **Step 2: Prepare the plan and print it in chat**

Call the MCP tool:

```text
prepare_youtrack_transfer(
  user_name="Oleg Litasov",
  issue_id=<user-supplied ID>,
  start="2026-10-01",
  end="2026-10-30"
)
```

Print every date, hours, source issues and replaced entry IDs/hours in chat.
Do not dump the raw JSON into the approval form.

- [ ] **Step 3: Ask for approval and write**

Call `write_plan(plan_id)`. The client must show the approval form; only an
explicit `approved: true` may proceed. If the user declines or the client cannot
show elicitation, report `blocked` and do not retry with another mechanism.

- [ ] **Step 4: Verify the result**

Call:

```text
get_worklogs(
  user_name="Oleg Litasov",
  tracker="redmine",
  start="2026-10-01",
  end="2026-10-30"
)
```

Confirm that every source date now has exactly one Redmine entry on the target
issue with the expected total hours and `development` comment. Report any
`failed` dates to the user.