from storage.database import (
    get_default_db_path,
    migrate_default_legacy_database,
    migrate_legacy_database,
)


def test_new_env_has_priority(monkeypatch, tmp_path):
    monkeypatch.setenv("WORK_ASSISTANT_DB", str(tmp_path / "new.db"))
    monkeypatch.setenv("FILL_REDMINE_DB", str(tmp_path / "old.db"))

    assert get_default_db_path() == tmp_path / "new.db"


def test_legacy_env_is_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("WORK_ASSISTANT_DB", raising=False)
    monkeypatch.setenv("FILL_REDMINE_DB", str(tmp_path / "old.db"))

    assert get_default_db_path() == tmp_path / "old.db"


def test_default_name_is_work_assistant(monkeypatch):
    monkeypatch.delenv("WORK_ASSISTANT_DB", raising=False)
    monkeypatch.delenv("FILL_REDMINE_DB", raising=False)

    assert get_default_db_path().name == "work_assistant.db"


def test_migrate_legacy_database_renames_file(tmp_path):
    legacy = tmp_path / "fill_redmine.db"
    target = tmp_path / "work_assistant.db"
    legacy.write_bytes(b"old-data")

    result = migrate_legacy_database(target, legacy, log=lambda message: None)

    assert result is True
    assert target.read_bytes() == b"old-data"
    assert not legacy.exists()


def test_migrate_legacy_database_keeps_existing_target(tmp_path):
    legacy = tmp_path / "fill_redmine.db"
    target = tmp_path / "work_assistant.db"
    legacy.write_bytes(b"old")
    target.write_bytes(b"new")

    result = migrate_legacy_database(target, legacy, log=lambda message: None)

    assert result is False
    assert target.read_bytes() == b"new"
    assert legacy.read_bytes() == b"old"


def test_migrate_default_skips_when_env_is_set(monkeypatch, tmp_path):
    monkeypatch.setenv("WORK_ASSISTANT_DB", str(tmp_path / "custom.db"))

    assert migrate_default_legacy_database(log=lambda message: None) is False
