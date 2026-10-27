"""Compute the metrics and trace a value back to its events."""

from __future__ import annotations

from datetime import datetime

from goldenpath.application.ports import EventStore
from goldenpath.domain import metrics
from goldenpath.domain.errors import DomainError
from goldenpath.domain.events import Event
from goldenpath.domain.metrics import LeadTime, ServiceMetrics


class NoEventsError(DomainError):
    """There is nothing to measure yet."""


SAMPLE_PREFIX = "sample-"


def _events(store: EventStore, include_samples: bool) -> list[Event]:
    """Every event, without the lesson's sample services (`sample-orders`, `sample-billing`) unless asked."""
    return [event for event in store.all() if include_samples or not event.service.startswith(SAMPLE_PREFIX)]


def summary(
    store: EventStore, start: datetime | None = None, end: datetime | None = None, include_samples: bool = False
) -> list[ServiceMetrics]:
    """One row per service over the data's own window, or over `[start, end)` when both are given."""
    events = _events(store, include_samples)
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    window = (start, end) if start and end else metrics.window_of(events)
    return [metrics.compute(events, name, window[0], window[1]) for name in metrics.services(events)]


def per_week(store: EventStore, include_samples: bool = False) -> list[tuple[int, list[ServiceMetrics]]]:
    """The metrics of every service for every week of the data."""
    events = _events(store, include_samples)
    if not events:
        raise NoEventsError("the event store is empty: run `make simulate` or deploy a service first")
    start, end = metrics.window_of(events)
    return metrics.weekly(events, start, end)


def trace(store: EventStore, service: str, commit: str) -> LeadTime:
    """The lead time of one commit with the commit event and the deployment event behind it."""
    return metrics.trace_lead_time(store.all(), service, commit)
