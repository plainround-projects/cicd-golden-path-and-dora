"""Integration tests need PostgreSQL from docker-compose.yml: `make up` first."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg
import pytest

from goldenpath.infrastructure.postgres_store import PostgresEventStore
from goldenpath.infrastructure.settings import Settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings.from_env()


@pytest.fixture
def store(settings: Settings) -> Iterator[PostgresEventStore]:
    """A store whose rows for the test services are removed before and after, so tests never see each other's data."""
    cleanup(settings)
    yield PostgresEventStore(settings.dsn)
    cleanup(settings)


def cleanup(settings: Settings) -> None:
    with psycopg.connect(settings.dsn) as connection:
        connection.execute("DELETE FROM events WHERE service LIKE 'it-%'")
