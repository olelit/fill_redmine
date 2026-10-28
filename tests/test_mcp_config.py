import json
from pathlib import Path

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


def _write_config(tmp_path, payload):
    path = tmp_path / "users.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _enabled_profile(name):
    return {"name": name, "is_enable": True}


def test_select_user_rejects_when_no_profiles_are_enabled(tmp_path):
    path = _write_config(tmp_path, {"users": [{"name": "me", "is_enable": False}]})

    with pytest.raises(ProfileConfigError):
        select_user(load_users(path))


def test_select_user_requires_name_when_multiple_profiles_are_enabled(tmp_path):
    path = _write_config(tmp_path, {"users": [_enabled_profile("a"), _enabled_profile("b")]})

    with pytest.raises(ProfileConfigError):
        select_user(load_users(path))


def test_select_user_returns_named_enabled_profile(tmp_path):
    path = _write_config(tmp_path, {"users": [_enabled_profile("a"), _enabled_profile("b")]})

    assert select_user(load_users(path), "b").name == "b"


def test_select_user_rejects_disabled_profile_name(tmp_path):
    path = _write_config(
        tmp_path,
        {"users": [_enabled_profile("a"), {"name": "b", "is_enable": False}]},
    )

    with pytest.raises(ProfileConfigError):
        select_user(load_users(path), "b")


def test_select_user_rejects_duplicate_enabled_profile_name(tmp_path):
    path = _write_config(
        tmp_path,
        {"users": [_enabled_profile("dup"), _enabled_profile("dup")]},
    )

    with pytest.raises(ProfileConfigError):
        select_user(load_users(path), "dup")


def test_select_user_rejects_unknown_profile_name(tmp_path):
    path = _write_config(tmp_path, {"users": [_enabled_profile("a")]})

    with pytest.raises(ProfileConfigError):
        select_user(load_users(path), "missing")


def test_profile_repr_hides_tracker_secrets(tmp_path):
    path = _write_config(
        tmp_path,
        {
            "users": [
                {
                    "name": "Oleg",
                    "is_enable": True,
                    "redmine": {"api_key": "REDMINE_SECRET_TOKEN"},
                    "youtrack": {"access_token": "YOUTRACK_SECRET_TOKEN"},
                }
            ]
        },
    )

    profile = load_users(path)[0]

    assert "REDMINE_SECRET_TOKEN" not in repr(profile)
    assert "YOUTRACK_SECRET_TOKEN" not in repr(profile)


def test_profile_errors_do_not_include_credentials(tmp_path):
    path = _write_config(
        tmp_path,
        {
            "users": [
                {
                    "name": "Oleg",
                    "is_enable": "yes",
                    "redmine": {"api_key": "REDMINE_SECRET_TOKEN"},
                    "youtrack": {"access_token": "YOUTRACK_SECRET_TOKEN"},
                }
            ]
        },
    )

    with pytest.raises(ProfileConfigError) as exc_info:
        load_users(path)

    message = str(exc_info.value)
    assert "REDMINE_SECRET_TOKEN" not in message
    assert "YOUTRACK_SECRET_TOKEN" not in message


def test_load_users_rejects_missing_file(tmp_path):
    with pytest.raises(ProfileConfigError):
        load_users(tmp_path / "missing.json")


def test_load_users_rejects_malformed_json(tmp_path):
    path = tmp_path / "users.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ProfileConfigError):
        load_users(path)


def test_load_users_rejects_non_list_users(tmp_path):
    path = _write_config(tmp_path, {"users": {}})

    with pytest.raises(ProfileConfigError):
        load_users(path)


def test_load_users_rejects_profile_that_is_not_an_object(tmp_path):
    path = _write_config(tmp_path, {"users": ["Oleg"]})

    with pytest.raises(ProfileConfigError):
        load_users(path)


def test_load_users_rejects_blank_name(tmp_path):
    path = _write_config(tmp_path, {"users": [{"name": "   ", "is_enable": True}]})

    with pytest.raises(ProfileConfigError):
        load_users(path)


@pytest.mark.parametrize("is_enable", [1, 0, "true", None])
def test_load_users_rejects_non_boolean_is_enable(tmp_path, is_enable):
    path = _write_config(tmp_path, {"users": [{"name": "Oleg", "is_enable": is_enable}]})

    with pytest.raises(ProfileConfigError):
        load_users(path)


def test_load_users_rejects_non_string_git_email(tmp_path):
    path = _write_config(
        tmp_path,
        {"users": [{"name": "Oleg", "is_enable": True, "git_email": 42}]},
    )

    with pytest.raises(ProfileConfigError):
        load_users(path)


@pytest.mark.parametrize("tracker", ["redmine", "youtrack"])
def test_load_users_rejects_non_object_tracker_block(tmp_path, tracker):
    path = _write_config(
        tmp_path,
        {"users": [{"name": "Oleg", "is_enable": True, tracker: "token"}]},
    )

    with pytest.raises(ProfileConfigError):
        load_users(path)


def test_load_users_allows_omitted_tracker_blocks(tmp_path):
    path = _write_config(tmp_path, {"users": [{"name": "Oleg", "is_enable": True}]})

    profile = load_users(path)[0]

    assert profile.git_email == ""
    assert profile.redmine == {}
    assert profile.youtrack == {}


def test_default_users_path_is_repo_relative(tmp_path, monkeypatch):
    from mcp_server import config as mcp_config

    expected = Path(mcp_config.__file__).resolve().parent.parent / "config" / "users.json"
    assert mcp_config.default_users_path() == expected

    monkeypatch.chdir(tmp_path)
    assert mcp_config.default_users_path() == expected


def test_example_config_is_tracked_and_disabled_without_usable_credentials():
    from mcp_server.config import default_users_path

    example = default_users_path().with_name("users.example.json")

    users = load_users(example)

    assert len(users) == 1
    profile = users[0]
    assert profile.name == "CHANGE_ME"
    assert profile.is_enable is False
    assert profile.redmine["api_key"] == ""
    assert profile.youtrack["access_token"] == ""
