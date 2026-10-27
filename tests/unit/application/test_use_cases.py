from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from goldenpath.application import measure
from goldenpath.application.generate_service import NonConformingServiceError, ServiceGenerator
from goldenpath.application.record_events import list_deployments, record
from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.errors import InvalidCatalogEntryError
from goldenpath.domain.events import Event, EventType
from goldenpath.domain.rules import Finding


class MemoryStore:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, events: Iterable[Event]) -> int:
        new = [event for event in events if event not in self.events]
        self.events.extend(new)
        return len(new)

    def all(self) -> list[Event]:
        return sorted(self.events, key=lambda event: event.ts)

    def clear(self) -> None:
        self.events.clear()


class Renderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Mapping[str, str]]] = []

    def render(self, destination: Path, substitutions: Mapping[str, str]) -> list[str]:
        self.calls.append((destination, substitutions))
        return ["README.md", "Makefile"]


class MemoryCatalog:
    def __init__(self) -> None:
        self.registered: list[CatalogEntry] = []

    def teams(self) -> frozenset[str]:
        return frozenset({"team-orders"})

    def register(self, entry: CatalogEntry) -> None:
        self.registered.append(entry)

    def entries(self) -> list[CatalogEntry]:
        return self.registered


class Repositories:
    def __init__(self) -> None:
        self.created: list[str] = []

    def create(self, directory: Path, name: str, message: str) -> str:
        self.created.append(name)
        return "c0ffee" * 6


class Auditor:
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings

    def audit(self, directory: Path) -> list[Finding]:
        return self.findings


def generator(findings: list[Finding] | None = None) -> tuple[ServiceGenerator, Renderer, MemoryCatalog, Repositories]:
    renderer, catalog, repositories = Renderer(), MemoryCatalog(), Repositories()
    clock = iter(range(100))
    return (
        ServiceGenerator(
            renderer, catalog, repositories, Auditor(findings or []), "f" * 40, clock=lambda: float(next(clock))
        ),
        renderer,
        catalog,
        repositories,
    )


def test_a_service_is_rendered_audited_registered_and_published_in_that_order():
    service_generator, renderer, catalog, repositories = generator()
    service = service_generator.generate(
        "orders", "team-orders", Path("/tmp/orders"), "https://wiki.example.com/runbooks"
    )
    assert renderer.calls[0][1]["__NAME__"] == "orders"
    assert renderer.calls[0][1]["__PLATFORM_REF__"] == "f" * 40
    assert [entry.name for entry in catalog.registered] == ["orders"]
    assert repositories.created == ["orders"]
    assert service.entry.runbook == "https://wiki.example.com/runbooks/orders"
    assert set(service.timings) == {"render", "audit", "publish"}


def test_a_person_as_owner_is_refused_before_anything_is_rendered():
    service_generator, renderer, _, repositories = generator()
    with pytest.raises(InvalidCatalogEntryError, match="not a person"):
        service_generator.generate("orders", "alice", Path("/tmp/x"), "https://wiki.example.com/runbooks")
    assert renderer.calls == []
    assert repositories.created == []


def test_a_repository_that_fails_the_audit_is_never_registered_or_published():
    finding = Finding("GP-SIGN", "signed artifacts", "no step signs the artifact")
    service_generator, _, catalog, repositories = generator([finding])
    with pytest.raises(NonConformingServiceError) as error:
        service_generator.generate("orders", "team-orders", Path("/tmp/x"), "https://wiki.example.com/runbooks")
    assert error.value.findings == [finding]
    assert catalog.registered == []
    assert repositories.created == []


def test_events_are_recorded_once_even_when_sent_twice():
    store = MemoryStore()
    event = Event(datetime(2026, 9, 1, tzinfo=UTC), "orders", EventType.COMMIT, "a1")
    assert record(store, [event]) == 1
    assert record(store, [event]) == 0


def test_every_deployment_of_a_service_is_listed_with_its_commits():
    store = MemoryStore()
    when = datetime(2026, 9, 1, 14, tzinfo=UTC)
    record(
        store, [Event(when, "orders", EventType.DEPLOY, "d1:a1+a2"), Event(when, "billing", EventType.DEPLOY, "e1:b1")]
    )
    assert list_deployments(store, "orders") == [("2026-09-01 14:00", "d1", ("a1", "a2"))]


def test_measuring_an_empty_store_says_what_to_do():
    with pytest.raises(measure.NoEventsError, match="empty"):
        measure.summary(MemoryStore())
    with pytest.raises(measure.NoEventsError):
        measure.per_week(MemoryStore())


def test_the_summary_and_the_trace_read_the_store():
    store = MemoryStore()
    record(
        store,
        [
            Event(datetime(2026, 9, 1, 9, tzinfo=UTC), "orders", EventType.COMMIT, "a1"),
            Event(datetime(2026, 9, 1, 14, tzinfo=UTC), "orders", EventType.DEPLOY, "d1:a1"),
        ],
    )
    (row,) = measure.summary(store)
    assert row.median_lead_time_hours == 5.0
    assert measure.trace(store, "orders", "a1").hours == 5.0
    assert [index for index, _ in measure.per_week(store)] == [1]
