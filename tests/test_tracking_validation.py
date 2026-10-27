from gui.tracking_validation import validate_tracking_request


def test_valid_request():
    data, errors = validate_tracking_request(
        user_ids=[1],
        destination="redmine",
        source="autofill",
        source_kind="",
        start_text="2026-10-01",
        end_text="2026-10-31",
    )
    assert errors == []
    assert data["destination"] == "redmine"
    assert data["start"].isoformat() == "2026-10-01"


def test_requires_users():
    data, errors = validate_tracking_request(
        [], "redmine", "autofill", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("юзера" in error.lower() for error in errors)


def test_tracker_source_cannot_equal_destination():
    data, errors = validate_tracking_request(
        [1], "redmine", "tracker", "redmine", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("совпадать" in error.lower() for error in errors)


def test_bad_period():
    data, errors = validate_tracking_request(
        [1], "redmine", "autofill", "", "2026-10-31", "2026-10-01"
    )
    assert data is None
    assert any("позже" in error.lower() for error in errors)


def test_tracker_source_requires_kind():
    data, errors = validate_tracking_request(
        [1], "redmine", "tracker", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("трекер-источник" in error.lower() for error in errors)


def test_bad_date_format():
    data, errors = validate_tracking_request(
        [1], "redmine", "autofill", "", "01.10.2026", "2026-10-31"
    )
    assert data is None
    assert any("формате" in error.lower() for error in errors)


def test_missing_destination():
    data, errors = validate_tracking_request(
        [1], "", "autofill", "", "2026-10-01", "2026-10-31"
    )
    assert data is None
    assert any("назначение" in error.lower() for error in errors)
