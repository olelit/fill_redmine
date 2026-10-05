from configs.user_config import MANUAL, YOUTRACK, UserConfig
from gui.validation import parse_exclude_date, validate_user_form


def valid_form(**overrides) -> dict[str, str]:
    form = {
        "name": "Олег",
        "driver": YOUTRACK,
        "redmine_api_key": "key",
        "user_id": "16",
        "activity_id": "9",
        "issue_id": "2682",
        "comment": "development",
        "youtrack_access_token": "token",
    }
    form.update(overrides)
    return form


class TestValidateUserForm:
    def test_valid_form_returns_user(self):
        user, errors = validate_user_form(
            valid_form(),
            is_enable=True,
            exclude_dates=["2026-10-01"],
            db_id=5,
        )

        assert errors == []
        assert isinstance(user, UserConfig)
        assert user.name == "Олег"
        assert user.user_id == 16
        assert user.activity_id == 9
        assert user.issue_id == 2682
        assert user.driver == YOUTRACK
        assert user.exclude_dates == ["2026-10-01"]
        assert user.db_id == 5

    def test_empty_name_is_rejected(self):
        user, errors = validate_user_form(valid_form(name="  "), is_enable=True, exclude_dates=[])

        assert user is None
        assert "Имя обязательно" in errors

    def test_non_integer_user_id_is_rejected(self):
        user, errors = validate_user_form(valid_form(user_id="abc"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("user_id" in error for error in errors)

    def test_zero_issue_id_is_rejected(self):
        user, errors = validate_user_form(valid_form(issue_id="0"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("issue_id" in error for error in errors)

    def test_youtrack_requires_token(self):
        user, errors = validate_user_form(
            valid_form(youtrack_access_token=""),
            is_enable=True,
            exclude_dates=[],
        )

        assert user is None
        assert any("token" in error.lower() for error in errors)

    def test_manual_does_not_require_token(self):
        user, errors = validate_user_form(
            valid_form(driver=MANUAL, youtrack_access_token=""),
            is_enable=True,
            exclude_dates=[],
        )

        assert errors == []
        assert user.driver == MANUAL

    def test_invalid_driver_is_rejected(self):
        user, errors = validate_user_form(valid_form(driver="jira"), is_enable=True, exclude_dates=[])

        assert user is None
        assert any("driver" in error for error in errors)


class TestParseExcludeDate:
    def test_valid_date_is_normalized(self):
        parsed, error = parse_exclude_date("2026-10-01", [])

        assert parsed == "2026-10-01"
        assert error is None

    def test_invalid_date_returns_error(self):
        parsed, error = parse_exclude_date("01.10.2026", [])

        assert parsed is None
        assert error is not None

    def test_duplicate_returns_error(self):
        parsed, error = parse_exclude_date("2026-10-01", ["2026-10-01"])

        assert parsed is None
        assert error is not None
