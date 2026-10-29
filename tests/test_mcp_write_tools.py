import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from mcp import types
from mcp.client import Client

from mcp_server.app import create_server
from mcp_server.config import ProfileConfigError, UserProfile
from mcp_server.plans import (
    PLAN_TTL_SECONDS,
    PlanError,
    PlanStore,
    PlannedEntry,
    fingerprint_target_config,
)
from mcp_server.writer import execute_plan


def _entry(**changes):
    values = {
        "date": "2026-10-20",
        "hours": 1.5,
        "comment": "Review changes",
        "commit_hashes": ("abc123",),
    }
    values.update(changes)
    return PlannedEntry(**values)


def _write_users(path: Path, users: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"users": users}), encoding="utf-8")


def _create_plan(store, user_name, kind, issue_id, entries, warnings, fingerprint="test"):
    return store.create(user_name, kind, issue_id, entries, warnings, fingerprint)


def _fingerprint(kind, config):
    profile = UserProfile(name="Oleg", is_enable=True, **{kind: config})
    return fingerprint_target_config(profile, kind)


def _tool_data(result):
    assert result.is_error is False
    return [json.loads(item.text) for item in result.content]


def test_plan_store_claims_once_and_rejects_unknown_ids():
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())

    assert store.claim(plan.plan_id) == plan
    with pytest.raises(PlanError):
        store.claim(plan.plan_id)
    with pytest.raises(PlanError):
        store.claim("unknown")


def test_plan_store_rejects_expired_plans_and_rechecks_freshness(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("mcp_server.plans.time.monotonic", lambda: now[0])
    store = PlanStore()
    expired = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())
    now[0] += PLAN_TTL_SECONDS

    with pytest.raises(PlanError):
        store.claim(expired.plan_id)

    fresh = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())
    claimed = store.claim(fresh.plan_id)
    now[0] += PLAN_TTL_SECONDS
    with pytest.raises(PlanError):
        store.validate_fresh(claimed)


@pytest.mark.parametrize(
    ("action", "approved", "with_capability", "expected_calls"),
    [
        ("accept", True, True, 1),
        ("accept", False, True, 0),
        ("decline", None, True, 0),
        ("cancel", None, True, 0),
        ("accept", True, False, 0),
    ],
)
def test_write_tool_only_executes_explicit_approval(
    action, approved, with_capability, expected_calls
):
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())
    executed = []

    def execute(claimed):
        executed.append(claimed)
        return {"results": []}

    server = create_server(write_store=store, write_executor=execute)

    async def elicitation_callback(context, params):
        if action == "accept":
            return types.ElicitResult(action=action, content={"approved": approved})
        return types.ElicitResult(action=action)

    async def call():
        async with Client(
            server,
            mode="legacy",
            elicitation_callback=elicitation_callback if with_capability else None,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    result = asyncio.run(call())

    assert len(executed) == expected_calls
    assert result.is_error is False
    if expected_calls:
        assert _tool_data(result) == [{"results": []}]
    else:
        assert "blocked" in json.dumps(_tool_data(result)).lower()


def test_write_tool_asks_with_plan_rows_and_no_credentials(tmp_path):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "youtrack": {
            "access_token": "private-token", "issue_id": "APP-42"
        }}],
    )
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "youtrack", "APP-42", (_entry(),), ())
    messages = []

    async def elicitation_callback(context, params):
        messages.append(params.message)
        assert params.requested_schema["properties"] == {"approved": {"type": "boolean"}}
        assert params.requested_schema["required"] == ["approved"]
        return types.ElicitResult(action="decline")

    async def call():
        async with Client(
            create_server(path, write_store=store, write_executor=lambda _plan: {}),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    asyncio.run(call())

    assert len(messages) == 1
    for expected in (
        "1 worklog",
        "1.5 ч",
        "Oleg",
        "YouTrack",
        "Подробный план",
    ):
        assert expected in messages[0]
    assert "private-token" not in messages[0]


def test_write_tool_approval_form_does_not_embed_plan_rows(tmp_path):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "youtrack": {
            "access_token": "private-token", "issue_id": "APP-42"
        }}],
    )
    comment = 'Fix | "urgent"\nUser | redmine | fake row'
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "youtrack", "APP-42", (_entry(comment=comment),), ())
    messages = []

    async def elicitation_callback(context, params):
        messages.append(params.message)
        return types.ElicitResult(action="decline")

    async def call_with_plan():
        async with Client(
            create_server(path, write_store=store, write_executor=lambda _plan: {}),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    asyncio.run(call_with_plan())

    message = messages[0]
    assert "Fix" not in message
    assert "fake row" not in message
    assert "APP-42" not in message
    assert "Review changes" not in message
    assert "private-token" not in message
    assert "Подробный план" in message


def test_write_tool_approval_form_shows_warning_count(tmp_path):
    path = tmp_path / "users.json"
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "youtrack": {
            "access_token": "private-token", "issue_id": "APP-42"
        }}],
    )
    store = PlanStore()
    plan = _create_plan(
        store,
        "Oleg",
        "youtrack",
        "APP-42",
        (
            _entry(),
            _entry(date="2026-10-21", comment="Fix bug", issue_id="APP-7"),
        ),
        ("Day 2026-10-20 has no commits",),
    )
    messages = []

    async def elicitation_callback(context, params):
        messages.append(params.message)
        return types.ElicitResult(action="decline")

    async def call():
        async with Client(
            create_server(path, write_store=store, write_executor=lambda _plan: {}),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    asyncio.run(call())

    assert len(messages) == 1
    message = messages[0]
    assert "Предупреждений: 1" in message
    assert "Day 2026-10-20 has no commits" not in message
    assert "APP-7" not in message
    assert "private-token" not in message


def test_write_tool_rechecks_freshness_after_approval(monkeypatch):
    now = [1.0]
    monkeypatch.setattr("mcp_server.plans.time.monotonic", lambda: now[0])
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())
    executed = []

    async def elicitation_callback(context, params):
        now[0] += PLAN_TTL_SECONDS
        return types.ElicitResult(action="accept", content={"approved": True})

    async def call():
        async with Client(
            create_server(write_store=store, write_executor=lambda plan: executed.append(plan)),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    result = asyncio.run(call())

    assert executed == []
    assert "blocked" in json.dumps(_tool_data(result)).lower()


def test_write_tool_rejects_unknown_and_replayed_plans_without_execution():
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())
    executed = []

    async def elicitation_callback(context, params):
        return types.ElicitResult(action="accept", content={"approved": True})

    async def call(plan_id):
        async with Client(
            create_server(
                write_store=store,
                write_executor=lambda value: (executed.append(value) or {}),
            ),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan_id})

    first = asyncio.run(call(plan.plan_id))
    replay = asyncio.run(call(plan.plan_id))
    unknown = asyncio.run(call("unknown"))

    assert len(executed) == 1
    assert first.is_error is False
    assert replay.is_error is False
    assert unknown.is_error is False
    assert "blocked" in json.dumps(_tool_data(replay)).lower()
    assert "blocked" in json.dumps(_tool_data(unknown)).lower()


def test_write_tool_does_not_convert_executor_errors_into_approval_results():
    store = PlanStore()
    plan = _create_plan(store, "Oleg", "redmine", "42", (_entry(),), ())

    def fail_write(_plan):
        raise RuntimeError("tracker write failed")

    async def elicitation_callback(context, params):
        return types.ElicitResult(action="accept", content={"approved": True})

    async def call():
        async with Client(
            create_server(
                write_store=store,
                write_executor=fail_write,
            ),
            mode="legacy",
            elicitation_callback=elicitation_callback,
        ) as client:
            return await client.call_tool("write_plan", {"plan_id": plan.plan_id})

    result = asyncio.run(call())

    assert result.is_error is True
    assert "blocked" not in result.content[0].text.lower()


def test_writer_reloads_enabled_profile_and_injects_redmine_issue(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    config = {"api_key": "current-secret", "user_id": 17, "activity_id": 9}
    _write_users(
        path,
        [{"name": "Oleg", "git_email": "old@example.com", "is_enable": True,
          "redmine": config}],
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
    )
    _write_users(
        path,
        [{"name": "Oleg", "git_email": "current@example.com", "is_enable": True,
          "redmine": config}],
    )
    calls = []

    class FakeTracker:
        def create_worklogs(self, records):
            calls.append((records, self.config["issue_id"]))
            return []

    def build(profile, kind, *, issue_id=None, for_write=False):
        tracker = FakeTracker()
        tracker.config = {"issue_id": issue_id}
        calls.append((profile.redmine["api_key"], profile.git_email, kind, for_write))
        return tracker

    monkeypatch.setattr("mcp_server.writer.build_user_tracker", build)

    result = execute_plan(plan, path)

    assert calls[0] == ("current-secret", "current@example.com", "redmine", True)
    records, issue_id = calls[1]
    assert issue_id == 42
    assert [(record.date, record.hours, record.description) for record in records] == [
        ("2026-10-20", 1.5, "Review changes")
    ]
    assert result == {
        "results": [{"date": "2026-10-20", "issue": "42", "status": "created"}]
    }
    assert "current-secret" not in json.dumps(result)


def test_writer_refuses_disabled_profile_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    _write_users(path, [{"name": "Oleg", "is_enable": False, "redmine": {
        "api_key": "secret", "user_id": 17, "activity_id": 9
    }}])
    plan = _create_plan(PlanStore(), "Oleg", "redmine", "42", (_entry(),), ())
    writes = []
    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *args, **kwargs: writes.append(True),
    )

    with pytest.raises(ProfileConfigError):
        execute_plan(plan, path)

    assert writes == []


def test_writer_groups_youtrack_entries_by_issue(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    config = {"access_token": "youtrack-secret", "issue_id": "APP-42"}
    _write_users(path, [{"name": "Oleg", "is_enable": True, "youtrack": config}])
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "youtrack",
        "APP-42",
        (
            _entry(),
            _entry(date="2026-10-21"),
            _entry(date="2026-10-22", issue_id="APP-7"),
        ),
        (),
        _fingerprint("youtrack", config),
    )
    builds = []
    written = []

    class FakeTracker:
        def __init__(self, issue_id):
            self.issue_id = issue_id

        def create_worklogs(self, records):
            written.append((self.issue_id, [record.date for record in records]))
            return []

    def build(profile, kind, *, issue_id=None, for_write=False):
        builds.append((kind, issue_id, for_write))
        return FakeTracker(issue_id)

    monkeypatch.setattr("mcp_server.writer.build_user_tracker", build)

    result = execute_plan(plan, path)

    assert builds == [
        ("youtrack", "APP-42", True),
        ("youtrack", "APP-7", True),
    ]
    assert written == [
        ("APP-42", ["2026-10-20", "2026-10-21"]),
        ("APP-7", ["2026-10-22"]),
    ]
    assert result == {
        "results": [
            {"date": "2026-10-20", "issue": "APP-42", "status": "created"},
            {"date": "2026-10-21", "issue": "APP-42", "status": "created"},
            {"date": "2026-10-22", "issue": "APP-7", "status": "created"},
        ]
    }
    assert "youtrack-secret" not in json.dumps(result)


def test_writer_failure_of_one_youtrack_issue_group_keeps_the_other(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    config = {"access_token": "youtrack-secret", "issue_id": "APP-42"}
    _write_users(path, [{"name": "Oleg", "is_enable": True, "youtrack": config}])
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "youtrack",
        "APP-42",
        (
            _entry(),
            _entry(date="2026-10-21", issue_id="APP-7"),
        ),
        (),
        _fingerprint("youtrack", config),
    )
    written = []

    class FakeTracker:
        def __init__(self, issue_id):
            self.issue_id = issue_id

        def create_worklogs(self, records):
            written.append([record.date for record in records])
            if self.issue_id == "APP-42":
                return [("2026-10-20", "secret server response")]
            return []

    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *a, issue_id=None, **k: FakeTracker(issue_id),
    )

    result = execute_plan(plan, path)

    assert written == [["2026-10-20"], ["2026-10-21"]]
    assert result == {
        "results": [
            {"date": "2026-10-20", "issue": "APP-42", "status": "failed"},
            {"date": "2026-10-21", "issue": "APP-7", "status": "created"},
        ]
    }
    assert "secret server response" not in json.dumps(result)


def test_writer_keeps_other_youtrack_issue_groups_when_one_group_raises(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    config = {"access_token": "youtrack-secret", "issue_id": "APP-42"}
    _write_users(path, [{"name": "Oleg", "is_enable": True, "youtrack": config}])
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "youtrack",
        "APP-42",
        (
            _entry(issue_id="APP-1"),
            _entry(date="2026-10-21", issue_id="APP-2"),
        ),
        (),
        _fingerprint("youtrack", config),
    )
    written = []

    class FakeTracker:
        def __init__(self, issue_id):
            self.issue_id = issue_id

        def create_worklogs(self, records):
            written.append(self.issue_id)
            if self.issue_id == "APP-1":
                raise RuntimeError("tracker exploded")
            return []

    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *a, issue_id=None, **k: FakeTracker(issue_id),
    )

    result = execute_plan(plan, path)

    assert written == ["APP-1", "APP-2"]
    assert result == {
        "results": [
            {"date": "2026-10-20", "issue": "APP-1", "status": "failed"},
            {"date": "2026-10-21", "issue": "APP-2", "status": "created"},
        ]
    }
    assert "tracker exploded" not in json.dumps(result)


def test_writer_refuses_empty_youtrack_issue_before_writing(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    config = {"access_token": "secret", "issue_id": "APP-42"}
    _write_users(path, [{"name": "Oleg", "is_enable": True, "youtrack": config}])
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "youtrack",
        "",
        (_entry(), _entry(date="2026-10-21", issue_id="APP-7")),
        (),
        _fingerprint("youtrack", config),
    )
    writes = []
    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *args, **kwargs: writes.append(True),
    )

    with pytest.raises(ProfileConfigError):
        execute_plan(plan, path)

    assert writes == []


def test_writer_refuses_changed_youtrack_config_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    old_config = {"access_token": "secret", "issue_id": "APP-OLD"}
    _write_users(path, [{"name": "Oleg", "is_enable": True, "youtrack": old_config}])
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "youtrack",
        "APP-OLD",
        (_entry(),),
        (),
        _fingerprint("youtrack", old_config),
    )
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "youtrack": {
            "access_token": "secret", "issue_id": "APP-NEW"
        }}],
    )
    writes = []
    monkeypatch.setattr(
        "mcp_server.writer.build_user_tracker",
        lambda *args, **kwargs: writes.append(True),
    )

    with pytest.raises(ProfileConfigError):
        execute_plan(plan, path)

    assert writes == []


def test_plan_store_accepts_same_date_for_different_issues():
    store = PlanStore()

    plan = _create_plan(
        store,
        "Oleg",
        "youtrack",
        "APP-42",
        (_entry(), _entry(issue_id="APP-7")),
        (),
    )

    assert [entry.issue_id for entry in plan.entries] == ["", "APP-7"]


def test_plan_store_rejects_duplicate_date_and_issue():
    store = PlanStore()

    with pytest.raises(ValueError, match="unique dates and issues"):
        store.create(
            "Oleg",
            "youtrack",
            "APP-42",
            (
                _entry(),
                _entry(issue_id="APP-42"),
            ),
            (),
            "test",
        )

    with pytest.raises(ValueError, match="unique dates and issues"):
        store.create(
            "Oleg",
            "youtrack",
            "APP-42",
            (
                _entry(issue_id="APP-7"),
                _entry(issue_id="APP-7"),
            ),
            (),
            "test",
        )


def test_plan_store_rejects_duplicate_entry_dates():
    store = PlanStore()

    with pytest.raises(ValueError, match="unique dates"):
        store.create(
            "Oleg",
            "redmine",
            "42",
            (_entry(), _entry(date="2026-10-20", hours=2.0)),
            (),
            "test",
        )


def test_writer_refuses_changed_target_config_before_building_tracker(tmp_path, monkeypatch):
    path = tmp_path / "users.json"
    initial_config = {"api_key": "original-secret", "user_id": 17, "activity_id": 9}
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "redmine": initial_config}],
    )
    plan = _create_plan(
        PlanStore(),
        "Oleg",
        "redmine",
        "42",
        (_entry(),),
        (),
        _fingerprint("redmine", initial_config),
    )
    _write_users(
        path,
        [{"name": "Oleg", "is_enable": True, "redmine": {
            "api_key": "changed-secret", "user_id": 17, "activity_id": 9
        }}],
    )
    assert plan.target_fingerprint not in repr(plan)
    writes = []

    class FakeTracker:
        def create_worklogs(self, records):
            writes.append(records)
            return []

    def build_tracker(*args, **kwargs):
        writes.append("built")
        return FakeTracker()

    monkeypatch.setattr("mcp_server.writer.build_user_tracker", build_tracker)

    with pytest.raises(ProfileConfigError, match="changed since plan creation"):
        execute_plan(plan, path)

    assert writes == []


def test_target_fingerprint_is_canonical_and_scoped_to_destination_block():
    redmine = {"user_id": 17, "api_key": "secret", "activity_id": 9}
    expected = hashlib.sha256(
        json.dumps(redmine, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    first = UserProfile(name="Oleg", is_enable=True, redmine=redmine)
    reordered = UserProfile(
        name="Another user",
        is_enable=False,
        git_email="changed@example.com",
        redmine={"activity_id": 9, "api_key": "secret", "user_id": 17},
        youtrack={"access_token": "unrelated-secret"},
    )

    assert fingerprint_target_config(first, "redmine") == expected
    assert fingerprint_target_config(reordered, "redmine") == expected
