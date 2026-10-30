import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time

from dto.git_commit_dto import GitCommitDTO

DEFAULT_WORKDAY_START: time = time(9, 0)
DEFAULT_COMMENT = "development"
ISSUE_PATTERN = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9]+-\d+)(?![A-Za-z0-9])")
ISSUE_PATTERN_ANY_CASE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9]+-\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
COMMENT_LIMIT = 255
UNITS_TOLERANCE = 1e-9


class AllocationError(ValueError):
    """Raised when commits cannot be allocated to a single day."""


@dataclass(frozen=True)
class CommitAllocation:
    issue: str
    hours: float
    comment: str
    commit_hashes: tuple[str, ...]
    weight_minutes: float


@dataclass(frozen=True)
class AllocationResult:
    allocations: tuple[CommitAllocation, ...]
    warnings: tuple[str, ...]


def find_issue_ids(
    text: str, project_keys: tuple[str, ...] = ()
) -> tuple[str, ...]:
    found: dict[str, None] = {}
    keys = {key.upper() for key in project_keys}
    if not keys:
        for match in ISSUE_PATTERN.finditer(text):
            found.setdefault(match.group(1), None)
        return tuple(found)
    for match in ISSUE_PATTERN_ANY_CASE.finditer(text):
        raw = match.group(1)
        issue = raw.upper()
        if raw == issue or issue.split("-", 1)[0] in keys:
            found.setdefault(issue, None)
    return tuple(found)


def allocate_commit_hours(
    commits: list[GitCommitDTO],
    *,
    day: date,
    hours: float,
    workday_start: time = DEFAULT_WORKDAY_START,
    fallback_issue: str | None = None,
    fallback_comment: str = DEFAULT_COMMENT,
    project_keys: tuple[str, ...] = (),
) -> AllocationResult:
    warnings: list[str] = []
    target_hours = float(hours)
    if not math.isfinite(target_hours):
        raise AllocationError(f"{day.isoformat()}: hours must be finite")

    timed = _sorted_commits(commits, day)
    target_units = math.floor(target_hours * 2 + UNITS_TOLERANCE)
    if target_units <= 0:
        warnings.append(f"{day.isoformat()}: no half-hour units to allocate")
        return AllocationResult((), tuple(warnings))

    weights, hashes, comments = _accumulate(
        timed, day, workday_start, fallback_issue, project_keys, warnings
    )
    if not weights:
        return AllocationResult((), tuple(warnings))

    ordered = sorted(weights, key=lambda issue: -weights[issue])
    kept = ordered
    if target_units < len(ordered):
        kept = ordered[:target_units]
        for issue in ordered[target_units:]:
            warnings.append(
                f"{day.isoformat()}: issue {issue} dropped: "
                f"not enough hours to allocate"
            )

    units = _distribute_units([(issue, weights[issue]) for issue in kept], target_units)
    allocations = tuple(
        CommitAllocation(
            issue=issue,
            hours=units[issue] / 2,
            comment=_comment(comments[issue], fallback_comment),
            commit_hashes=hashes[issue],
            weight_minutes=weights[issue],
        )
        for issue in kept
    )
    return AllocationResult(allocations, tuple(warnings))


def _sorted_commits(
    commits: list[GitCommitDTO], day: date
) -> list[tuple[datetime, GitCommitDTO]]:
    timed = [(_commit_moment(item, day), item) for item in commits]
    timed.sort(key=lambda pair: pair[0])
    return timed


def _commit_moment(item: GitCommitDTO, day: date) -> datetime:
    raw = item.date
    try:
        moment = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        raise AllocationError(
            f"{day.isoformat()}: invalid commit date {raw!r}"
        ) from None
    if moment.tzinfo is not None:
        moment = moment.replace(tzinfo=None)
    if moment.date() != day:
        raise AllocationError(
            f"{day.isoformat()}: commit {item.hash} belongs to "
            f"{moment.date().isoformat()}"
        )
    return moment


def _accumulate(
    timed: list[tuple[datetime, GitCommitDTO]],
    day: date,
    workday_start: time,
    fallback_issue: str | None,
    project_keys: tuple[str, ...],
    warnings: list[str],
) -> tuple[dict[str, float], dict[str, tuple[str, ...]], dict[str, str]]:
    weights: dict[str, float] = {}
    hashes: dict[str, list[str]] = {}
    comments: dict[str, str] = {}
    cursor = _minutes(workday_start)

    for moment, item in timed:
        commit_minutes = _minutes(moment)
        weight = max(1.0, commit_minutes - cursor)
        cursor = max(cursor, commit_minutes)

        issues = find_issue_ids(
            f"{item.subject}\n{item.body}", project_keys=project_keys
        )
        if not issues:
            fallback = _fallback(fallback_issue)
            if fallback is None:
                warnings.append(
                    f"{day.isoformat()}: commit {item.hash} has no issue "
                    f"reference; its interval was redistributed"
                )
                continue
            issues = (fallback,)

        share = weight / len(issues)
        for issue in issues:
            weights[issue] = weights.get(issue, 0.0) + share
            known = hashes.setdefault(issue, [])
            if item.hash not in known:
                known.append(item.hash)
            comments[issue] = item.subject

    frozen_hashes = {issue: tuple(items) for issue, items in hashes.items()}
    return weights, frozen_hashes, comments


def _distribute_units(
    ordered_weights: list[tuple[str, float]], target_units: int
) -> dict[str, int]:
    units = {issue: 1 for issue, _ in ordered_weights}
    extra = target_units - len(ordered_weights)
    if extra <= 0:
        return units

    total_weight = sum(weight for _, weight in ordered_weights)
    floors: dict[str, int] = {}
    remainders: list[tuple[float, int, str]] = []
    for index, (issue, weight) in enumerate(ordered_weights):
        ideal = extra * weight / total_weight
        whole = math.floor(ideal)
        floors[issue] = whole
        remainders.append((ideal - whole, -index, issue))

    assigned = sum(floors.values())
    remainders.sort(reverse=True)
    for _, _, issue in remainders[: extra - assigned]:
        floors[issue] += 1
    for issue, whole in floors.items():
        units[issue] = 1 + whole
    return units


def _comment(subject: str, fallback: str) -> str:
    comment = subject.strip() or fallback.strip()
    return comment[:COMMENT_LIMIT]


def _fallback(raw: str | None) -> str | None:
    value = (raw or "").strip().upper()
    return value or None


def _minutes(value: datetime | time) -> float:
    return (
        value.hour * 60
        + value.minute
        + value.second / 60
        + value.microsecond / 60_000_000
    )