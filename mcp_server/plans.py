import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass, field

from mcp_server.config import UserProfile


PLAN_TTL_SECONDS = 600


class PlanError(Exception):
    """Raised when a write plan cannot be claimed or is no longer fresh."""


@dataclass(frozen=True)
class PlannedEntry:
    date: str
    hours: float
    comment: str
    commit_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_hashes", tuple(self.commit_hashes))


@dataclass(frozen=True)
class WritePlan:
    plan_id: str
    user_name: str
    destination_kind: str
    issue_id: str
    entries: tuple[PlannedEntry, ...]
    warnings: tuple[str, ...]
    target_fingerprint: str = field(repr=False)
    created_at: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        object.__setattr__(self, "warnings", tuple(self.warnings))


def fingerprint_target_config(profile: UserProfile, destination_kind: str) -> str:
    if destination_kind not in ("redmine", "youtrack"):
        raise ValueError("Unsupported destination tracker")
    canonical_config = json.dumps(
        getattr(profile, destination_kind),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_config.encode("utf-8")).hexdigest()


class PlanStore:
    def __init__(self) -> None:
        self._plans: dict[str, WritePlan] = {}
        self._lock = threading.Lock()

    def create(
        self,
        user_name: str,
        destination_kind: str,
        issue_id: str,
        entries: tuple[PlannedEntry, ...],
        warnings: tuple[str, ...],
        target_fingerprint: str,
    ) -> WritePlan:
        entries = tuple(entries)
        if len({entry.date for entry in entries}) != len(entries):
            raise ValueError("Plan entries must have unique dates")
        plan = WritePlan(
            plan_id=secrets.token_urlsafe(24),
            user_name=user_name,
            destination_kind=destination_kind,
            issue_id=issue_id,
            entries=entries,
            warnings=tuple(warnings),
            target_fingerprint=target_fingerprint,
            created_at=time.monotonic(),
        )
        with self._lock:
            self._plans[plan.plan_id] = plan
        return plan

    def claim(self, plan_id: str) -> WritePlan:
        with self._lock:
            plan = self._plans.pop(plan_id, None)
        if plan is None:
            raise PlanError("Write plan is unavailable")
        self.validate_fresh(plan)
        return plan

    def validate_fresh(self, plan: WritePlan) -> None:
        if time.monotonic() - plan.created_at >= PLAN_TTL_SECONDS:
            raise PlanError("Write plan has expired")
