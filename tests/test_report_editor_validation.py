import math

from gui.report_editor import validate_report_row


def test_valid_row():
    hours, errors = validate_report_row("4", "development")
    assert errors == []
    assert hours == 4


def test_half_step_required():
    hours, errors = validate_report_row("4.3", "development")
    assert hours is None
    assert any("0.5" in error for error in errors)


def test_comment_defaults():
    hours, errors = validate_report_row("4", "  ")
    assert errors == []
    assert hours == 4


def test_comma_decimal_separator():
    hours, errors = validate_report_row(" 4,5 ", "development")
    assert errors == []
    assert hours == 4.5


def test_half_step_accepts_even_and_half():
    for text in ("0.5", "1", "1.5", "8", "23.5", "24"):
        hours, errors = validate_report_row(text, "development")
        assert errors == [], text
        assert math.isclose(hours, float(text)), text


def test_non_numeric_hours():
    hours, errors = validate_report_row("четыре", "development")
    assert hours is None
    assert any("числом" in error for error in errors)


def test_zero_and_negative_hours():
    for text in ("0", "-1", "-0.5"):
        hours, errors = validate_report_row(text, "development")
        assert hours is None
        assert any("больше нуля" in error for error in errors), text


def test_hours_above_day():
    hours, errors = validate_report_row("24.5", "development")
    assert hours is None
    assert any("24" in error for error in errors)


def test_nan_and_infinity_are_rejected():
    for text in ("nan", "inf", "-inf"):
        hours, errors = validate_report_row(text, "development")
        assert hours is None
        assert errors == ["Часы должны быть числом"], text
