from datetime import date, time

import pytest

from dto.git_commit_dto import GitCommitDTO
from mcp_server.commit_allocation import (
    DEFAULT_WORKDAY_START,
    AllocationError,
    allocate_commit_hours,
    find_issue_ids,
)

DAY = date(2026, 10, 30)


def commit(short_hash: str, at: str, subject: str, body: str = "") -> GitCommitDTO:
    return GitCommitDTO(
        hash=short_hash,
        author_name="Oleg",
        author_email="oleg@example.com",
        date=f"2026-10-30T{at}:00+03:00",
        subject=subject,
        body=body,
    )


def by_issue(result):
    return {item.issue: item.hours for item in result.allocations}


def test_find_issue_ids_is_case_insensitive_and_deduped():
    text = "fix abc-12 and ABC-12, also DRIVEO-7\nrefs XYZ-99"

    assert find_issue_ids(text, project_keys=("ABC", "DRIVEO", "XYZ")) == (
        "ABC-12",
        "DRIVEO-7",
        "XYZ-99",
    )


def test_find_issue_ids_matches_uppercase_only_by_default():
    assert find_issue_ids("fix abc-12 and DRIVEO-7") == ("DRIVEO-7",)


def test_find_issue_ids_ignores_technical_tokens():
    assert find_issue_ids("fix utf-8 and sha-256") == ()


def test_find_issue_ids_ignores_technical_tokens_with_project_keys():
    assert find_issue_ids("fix utf-8 and sha-256", project_keys=("DRIVEO",)) == ()


def test_find_issue_ids_accepts_case_insensitive_with_project_keys():
    assert find_issue_ids("fix driveo-7", project_keys=("DRIVEO",)) == (
        "DRIVEO-7",
    )


def test_find_issue_ids_keeps_uppercase_tags_outside_project_keys():
    assert find_issue_ids("PROJ-42 work", project_keys=("DRIVEO",)) == (
        "PROJ-42",
    )


def test_find_issue_ids_ignores_longer_tokens():
    text = "1ABC-3 and ABC-1a and seeABC-1x and ok PRJ-5, then abc-7."

    assert find_issue_ids(text, project_keys=("ABC", "PRJ")) == ("PRJ-5", "ABC-7")


def test_default_workday_start_is_nine():
    assert DEFAULT_WORKDAY_START == time(9, 0)


def test_allocates_proportionally_to_commit_intervals():
    commits = [
        commit("a1", "10:00", "DRIVEO-1 first"),
        commit("b1", "13:30", "DRIVEO-2 review"),
        commit("a2", "17:00", "DRIVEO-1 wrap up"),
    ]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    assert by_issue(result) == {"DRIVEO-1": 4.5, "DRIVEO-2": 3.5}
    assert result.warnings == ()
    first = result.allocations[0]
    assert first.comment == "DRIVEO-1 wrap up"
    assert first.commit_hashes == ("a1", "a2")


def test_splits_commit_between_multiple_issues():
    commits = [commit("a1", "10:00", "DRIVEO-1 DRIVEO-2 shared work")]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    assert by_issue(result) == {"DRIVEO-1": 4.0, "DRIVEO-2": 4.0}
    assert result.allocations[0].commit_hashes == ("a1",)
    assert result.allocations[1].commit_hashes == ("a1",)


def test_finds_issues_in_commit_body():
    commits = [commit("a1", "10:00", "misc cleanup", body="refs DRIVEO-4 and AB-2")]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    assert by_issue(result) == {"DRIVEO-4": 4.0, "AB-2": 4.0}


def test_respects_custom_workday_start():
    commits = [
        commit("a1", "10:00", "DRIVEO-1 early"),
        commit("b1", "13:00", "DRIVEO-2 later"),
    ]

    result = allocate_commit_hours(
        commits, day=DAY, hours=8.0, workday_start=time(12, 0)
    )

    weights = {item.issue: item.weight_minutes for item in result.allocations}
    assert weights == {"DRIVEO-1": 1.0, "DRIVEO-2": 60.0}


def test_uses_fallback_for_commit_without_issue():
    commits = [commit("a1", "10:00", "misc cleanup")]

    result = allocate_commit_hours(
        commits, day=DAY, hours=8.0, fallback_issue="DRIVEO-9"
    )

    assert by_issue(result) == {"DRIVEO-9": 8.0}
    assert result.warnings == ()


def test_rounds_to_half_hours_and_sums_exactly():
    commits = [
        commit("a1", "10:00", "DRIVEO-1 start"),
        commit("a2", "10:45", "DRIVEO-1 continue"),
        commit("b1", "12:00", "DRIVEO-2 review"),
        commit("c1", "15:00", "DRIVEO-3 refine"),
    ]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    total = sum(item.hours for item in result.allocations)
    assert total == pytest.approx(8.0)
    assert abs(total - 8.0) < 1e-9
    for item in result.allocations:
        doubled = item.hours * 2
        assert abs(doubled - round(doubled)) < 1e-9
        assert item.hours > 0


def test_drops_lowest_weight_issue_when_hours_too_small():
    commits = [
        commit("a1", "10:00", "DRIVEO-1 quick"),
        commit("b1", "12:00", "DRIVEO-2 long"),
        commit("c1", "13:00", "DRIVEO-3 last"),
    ]

    result = allocate_commit_hours(commits, day=DAY, hours=0.5)

    assert len(result.allocations) == 1
    assert result.allocations[0].issue == "DRIVEO-2"
    assert result.allocations[0].hours == 0.5
    dropped = [warning for warning in result.warnings if "dropped" in warning]
    assert len(dropped) == 2
    assert any("DRIVEO-1" in warning for warning in dropped)
    assert any("DRIVEO-3" in warning for warning in dropped)


def test_minimum_weight_keeps_zero_interval_commit():
    commits = [
        commit("a1", "09:00", "DRIVEO-1 first"),
        commit("b1", "09:00", "DRIVEO-2 second"),
    ]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    assert by_issue(result) == {"DRIVEO-1": 4.0, "DRIVEO-2": 4.0}


def test_invalid_commit_date_raises():
    bad = GitCommitDTO(
        hash="a1",
        author_name="Oleg",
        author_email="oleg@example.com",
        date="not-a-date",
        subject="DRIVEO-1 work",
    )

    with pytest.raises(AllocationError):
        allocate_commit_hours([bad], day=DAY, hours=8.0)


def test_invalid_commit_date_raises_even_with_zero_hours():
    bad = GitCommitDTO(
        hash="a1",
        author_name="Oleg",
        author_email="oleg@example.com",
        date="not-a-date",
        subject="DRIVEO-1 work",
    )

    with pytest.raises(AllocationError):
        allocate_commit_hours([bad], day=DAY, hours=0.0)


@pytest.mark.parametrize("hours", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_hours_raises_allocation_error(hours):
    commits = [commit("a1", "10:00", "DRIVEO-1 work")]

    with pytest.raises(AllocationError):
        allocate_commit_hours(commits, day=DAY, hours=hours)


def test_commit_from_another_day_raises():
    foreign = commit("a1", "10:00", "DRIVEO-1 work")
    foreign.date = "2026-10-29T10:00:00+03:00"

    with pytest.raises(AllocationError):
        allocate_commit_hours([foreign], day=DAY, hours=8.0)


def test_empty_commits_returns_empty():
    result = allocate_commit_hours([], day=DAY, hours=8.0)

    assert result.allocations == ()
    assert result.warnings == ()


def test_zero_target_units_returns_empty_with_warning():
    commits = [commit("a1", "10:00", "DRIVEO-1 work")]

    result = allocate_commit_hours(commits, day=DAY, hours=0.0)

    assert result.allocations == ()
    assert len(result.warnings) == 1


def test_skipped_commit_without_issue_reports_warning():
    commits = [
        commit("a1", "10:00", "DRIVEO-1 work"),
        commit("b1", "12:00", "no reference here"),
    ]

    result = allocate_commit_hours(commits, day=DAY, hours=8.0)

    assert by_issue(result) == {"DRIVEO-1": 8.0}
    assert any("b1" in warning for warning in result.warnings)
    assert any("redistributed" in warning for warning in result.warnings)