"""Compute the metrics and trace a value back to its events."""

from __future__ import annotations

from datetime import datetime

from goldenpath.application.ports import EventStore
from goldenpath.domain import metrics
from goldenpath.domain.errors import DomainError
from goldenpath.domain.metrics import LeadTime, ServiceMetrics


class NoEventsError(DomainError):
    """There is nothing to measure yet."""


def summary(store: EventStore, start: datetime | None = None, end: datetime | None = None) -> list[ServiceMetrics]:
    """One row per service over the data's own window, or over `[start, end)` when both are given."""
    events = store.all()
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    window = (start, end) if start and end else metrics.window_of(events)
    return [metrics.compute(events, name, window[0], window[1]) for name in metrics.services(events)]


def per_week(store: EventStore) -> list[tuple[int, list[ServiceMetrics]]]:
    """The metrics of every service for every week of the data."""
    events = store.all()
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    start, end = metrics.window_of(events)
    return metrics.weekly(events, start, end)


def trace(store: EventStore, service: str, commit: str) -> LeadTime:
    """The lead time of one commit with the commit event and the deployment event behind it."""
    return metrics.trace_lead_time(store.all(), service, commit)
