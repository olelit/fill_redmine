import pytest

from gui.formatting import format_hours


class TestFormatHours:
    def test_integer_hours(self):
        assert format_hours(8) == "8"

    def test_fractional_hours(self):
        assert format_hours(7.5) == "7.5"

    @pytest.mark.parametrize(
        ("hours", "expected"),
        [
            (0, "0"),
            (0.5, "0.5"),
            (1.25, "1.25"),
            (24, "24"),
        ],
    )
    def test_various_values(self, hours: int | float, expected: str):
        assert format_hours(hours) == expected
