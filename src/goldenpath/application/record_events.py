"""Record delivery events and read them back."""

from __future__ import annotations

from collections.abc import Iterable

from goldenpath.application.ports import EventSink, EventStore
from goldenpath.domain.events import Event, EventType, parse_deploy_ref


def record(sink: EventSink, events: Iterable[Event]) -> int:
    """Append events; duplicates are ignored. Returns how many were new."""
    return sink.append(events)


def list_deployments(store: EventStore, service: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """Every production deployment of a service as `(deployed at, deployment id, commits)`, oldest first (step 4)."""
    rows = []
    for event in store.all():
        if event.service == service and event.type is EventType.DEPLOY:
            parsed = parse_deploy_ref(event.ref)
            rows.append((event.ts.strftime("%Y-%m-%d %H:%M"), parsed.deployment, parsed.commits))
    return rows
