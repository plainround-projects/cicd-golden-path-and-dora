"""Delivery events: the facts every DORA metric is computed from. Nothing else is read, not even the Git history."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from goldenpath.domain.errors import InvalidEventError

_SERVICE: Final = re.compile(r"^[a-z][a-z0-9-]{1,38}$")
_REF: Final = re.compile(r"^[A-Za-z0-9._:+-]{1,200}$")


class EventType(StrEnum):
    """What happened: a commit entered the pipeline, a deployment reached production, failed, or was restored."""

    COMMIT = "commit"
    DEPLOY = "deploy"
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass(frozen=True, slots=True)
class Event:
    """One delivery event. `ref` is a commit id, or for a deployment `<id>:<commit>+<commit>`, or a deployment id.

    `ts` is UTC and comes from the pipeline's clock for every event type (never from a developer-set field).
    `detail` says why a deployment failed (`rollback`, `incident`, `health-check`, `signature`); empty otherwise.
    """

    ts: datetime
    service: str
    type: EventType
    ref: str
    detail: str = ""

    def __post_init__(self) -> None:
        """Refuse an event that cannot be placed on a timeline."""
        if self.ts.tzinfo is None:
            raise InvalidEventError("ts must carry a time zone (UTC)")
        if not _SERVICE.match(self.service):
            raise InvalidEventError(f"service must be 2-39 characters of a-z, 0-9 and '-', got {self.service!r}")
        if not _REF.match(self.ref):
            raise InvalidEventError(f"ref must be 1-200 characters of letters, digits and . _ : + -, got {self.ref!r}")
        if self.type is EventType.DEPLOY and ":" not in self.ref:
            raise InvalidEventError("a deploy ref looks like 'd1:a1+a2' (deployment id, then its commits)")
        if self.detail and self.type is not EventType.FAILED:
            raise InvalidEventError("only a failed event carries a detail")


def parse_timestamp(text: str) -> datetime:
    """`2026-09-01T09:00` (minutes, UTC) or any ISO 8601 time with an offset."""
    parsed = datetime.fromisoformat(text.strip())
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DeployRef:
    """The two halves of a deploy ref: the deployment's id and its commits (none: an empty deploy)."""

    deployment: str
    commits: tuple[str, ...]


def parse_deploy_ref(ref: str) -> DeployRef:
    """`d1:a1+a2` becomes ('d1', ('a1', 'a2')); `d9:` is a deployment with no commits."""
    deployment, _, rest = ref.partition(":")
    return DeployRef(deployment, tuple(part for part in rest.split("+") if part))


def format_deploy_ref(deployment: str, commits: tuple[str, ...] | list[str]) -> str:
    """The inverse of `parse_deploy_ref`."""
    return f"{deployment}:{'+'.join(commits)}"
