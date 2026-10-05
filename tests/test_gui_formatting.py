from dto.preview_dto import DateRangeDTO
from gui.formatting import format_hours, format_range, format_ranges


class TestFormatHours:
    def test_integer_hours(self):
        assert format_hours(8) == "8"

    def test_fractional_hours(self):
        assert format_hours(7.5) == "7.5"


class TestFormatRange:
    def test_single_day(self):
        rng = DateRangeDTO(start_date="2026-10-01", end_date="2026-10-01", hours=8)

        assert format_range(rng) == "01.10 — 8h"

    def test_period(self):
        rng = DateRangeDTO(start_date="2026-10-01", end_date="2026-10-04", hours=8)

        assert format_range(rng) == "01.10–04.10 — 8h"


class TestFormatRanges:
    def test_empty_list(self):
        assert format_ranges([]) == ""

    def test_multiple_ranges_joined(self):
        ranges = [
            DateRangeDTO(start_date="2026-10-01", end_date="2026-10-02", hours=8),
            DateRangeDTO(start_date="2026-10-05", end_date="2026-10-05", hours=4),
        ]

        assert format_ranges(ranges) == "01.10–02.10 — 8h; 05.10 — 4h"
