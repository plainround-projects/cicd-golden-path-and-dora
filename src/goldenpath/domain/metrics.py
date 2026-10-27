"""The four DORA metrics, computed per service from events only.

- Deployment frequency: production deployments per week (one with no commit does not count: `empty_deploys`).
- Lead time for changes: from a commit event to the deployment event containing it, per commit; the median.
- Change fail rate: the share of deployments followed by a `failed` event.
- Recovery time: from `failed` to the next `recovered` for the same deployment; reported as the median.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from goldenpath.domain.errors import UnknownCommitError
from goldenpath.domain.events import Event, EventType, parse_deploy_ref

WEEK = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ServiceMetrics:
    """The four metrics of one service over a window, plus the numbers that keep them honest."""

    service: str
    window_start: datetime
    window_end: datetime
    deploys: int
    empty_deploys: int
    deploys_per_week: float
    median_lead_time_hours: float | None
    change_fail_rate: float | None
    median_recovery_minutes: float | None
    median_batch_size: float | None
    open_failures: int


@dataclass(frozen=True, slots=True)
class LeadTime:
    """One lead time, with the two events it is the difference of (step 5: trace a value to its events)."""

    commit: Event
    deploy: Event
    hours: float


def _in_window(event: Event, start: datetime, end: datetime) -> bool:
    return start <= event.ts < end


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def lead_times(events: Iterable[Event], service: str) -> list[LeadTime]:
    """Every commit of `service` that reached a deployment, with its lead time."""
    commits = {event.ref: event for event in events if event.service == service and event.type is EventType.COMMIT}
    result = []
    for event in events:
        if event.service == service and event.type is EventType.DEPLOY:
            for commit_ref in parse_deploy_ref(event.ref).commits:
                commit = commits.get(commit_ref)
                if commit is not None:
                    result.append(LeadTime(commit, event, (event.ts - commit.ts).total_seconds() / 3600))
    return result


def trace_lead_time(events: Sequence[Event], service: str, commit_ref: str) -> LeadTime:
    """The lead time of one commit and the two events behind it."""
    for lead in lead_times(events, service):
        if lead.commit.ref == commit_ref:
            return lead
    raise UnknownCommitError(f"{service}: no commit {commit_ref!r} with a deployment")


def compute(events: Sequence[Event], service: str, start: datetime, end: datetime) -> ServiceMetrics:
    """The metrics of one service for deployments inside `[start, end)`."""
    own = [event for event in events if event.service == service]
    deploys = [event for event in own if event.type is EventType.DEPLOY and _in_window(event, start, end)]
    real = [event for event in deploys if parse_deploy_ref(event.ref).commits]
    ids = {parse_deploy_ref(event.ref).deployment: event for event in real}
    failures = [event for event in own if event.type is EventType.FAILED and event.ref in ids]
    recoveries = defaultdict(list)
    for event in own:
        if event.type is EventType.RECOVERED:
            recoveries[event.ref].append(event.ts)
    recovery_minutes: list[float] = []
    open_failures = 0
    for failure in failures:
        later = [ts for ts in recoveries[failure.ref] if ts >= failure.ts]
        if later:
            recovery_minutes.append((min(later) - failure.ts).total_seconds() / 60)
        else:
            open_failures += 1
    window_leads = [lead.hours for lead in lead_times(own, service) if _in_window(lead.deploy, start, end)]
    weeks = (end - start) / WEEK
    return ServiceMetrics(
        service=service,
        window_start=start,
        window_end=end,
        deploys=len(real),
        empty_deploys=len(deploys) - len(real),
        deploys_per_week=len(real) / weeks if weeks else 0.0,
        median_lead_time_hours=_median(window_leads),
        change_fail_rate=len({failure.ref for failure in failures}) / len(real) if real else None,
        median_recovery_minutes=_median(recovery_minutes),
        median_batch_size=_median([float(len(parse_deploy_ref(event.ref).commits)) for event in real]),
        open_failures=open_failures,
    )


def services(events: Iterable[Event]) -> list[str]:
    """The services that have any event, sorted."""
    return sorted({event.service for event in events})


def window_of(events: Sequence[Event]) -> tuple[datetime, datetime]:
    """The data's own window: midnight of the first day, in whole weeks, up to the week of the last event."""
    first = min(event.ts for event in events)
    last = max(event.ts for event in events)
    start = first.replace(hour=0, minute=0, second=0, microsecond=0)
    weeks = max(1, -(-(last - start) // WEEK))
    return start, start + weeks * WEEK


def weekly(events: Sequence[Event], start: datetime, end: datetime) -> list[tuple[int, list[ServiceMetrics]]]:
    """Per week (counted from `start`), the metrics of every service."""
    table = []
    index = 1
    cursor = start
    while cursor < end:
        table.append((index, [compute(events, name, cursor, cursor + WEEK) for name in services(events)]))
        cursor += WEEK
        index += 1
    return table
