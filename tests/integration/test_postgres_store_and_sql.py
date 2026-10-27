"""The store and the SQL on real PostgreSQL: the SQL answers must equal the Python domain's on the sample."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from goldenpath.domain import metrics
from goldenpath.domain.events import Event, EventType
from goldenpath.infrastructure.csv_store import CsvEventStore

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)

pytestmark = pytest.mark.integration


def sample_with_prefix() -> list[Event]:
    return [
        Event(event.ts, f"it-{event.service}", event.type, event.ref, event.detail)
        for event in CsvEventStore(ROOT / "data" / "events-sample.csv").all()
    ]


def test_events_round_trip_and_a_duplicate_is_ignored(store):
    events = [
        Event(NOW, "it-orders", EventType.COMMIT, "a1"),
        Event(NOW, "it-orders", EventType.FAILED, "d1", "rollback"),
    ]
    assert store.append(events) == 2
    assert store.append(events) == 0
    assert [event for event in store.all() if event.service == "it-orders"] == events


def test_the_schema_refuses_what_the_domain_refuses(store, settings):
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute("INSERT INTO events (ts, service, type, ref) VALUES (now(), 'it-x', 'teleport', 'a1')")
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute("INSERT INTO events (ts, service, type, ref) VALUES (now(), 'it-x', 'deploy', 'no-colon')")
    with psycopg.connect(settings.dsn) as connection, pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(
            "INSERT INTO events (ts, service, type, ref, detail) VALUES (now(), 'it-x', 'commit', 'a1', 'why')"
        )


def test_sql_and_python_give_the_lessons_numbers_for_the_sample(store, settings):
    store.append(sample_with_prefix())
    events = [event for event in store.all() if event.service.startswith("it-")]
    start, end = metrics.window_of(events)
    python = {
        row.service: row for row in (metrics.compute(events, name, start, end) for name in metrics.services(events))
    }
    with psycopg.connect(settings.dsn) as connection:
        rows = connection.execute(
            """
            WITH real AS (
              SELECT DISTINCT service, deploy_id, deployed_at FROM deploy_commits
              WHERE commit_ref IS NOT NULL AND service LIKE 'it-%'
            )
            SELECT r.service,
                   count(*),
                   (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY l.hours)
                    FROM lead_times l WHERE l.service = r.service),
                   (SELECT count(DISTINCT f.ref) FROM events f WHERE f.service = r.service AND f.type = 'failed')
            FROM real r GROUP BY r.service ORDER BY r.service
            """
        ).fetchall()
    sql = {service: (deploys, lead, failed) for service, deploys, lead, failed in rows}
    assert sql["it-orders"] == (4, 4.0, 1)
    assert sql["it-billing"] == (1, 62.0, 1)
    assert python["it-orders"].median_lead_time_hours == sql["it-orders"][1]
    assert python["it-billing"].median_lead_time_hours == sql["it-billing"][1]
    assert python["it-orders"].change_fail_rate == sql["it-orders"][2] / sql["it-orders"][0]


def test_the_queries_file_runs_against_the_seed_and_prints_the_lessons_table(settings):
    seed = (ROOT / "sql" / "002_seed.sql").read_text()
    queries = (ROOT / "sql" / "003_queries.sql").read_text()
    with psycopg.connect(settings.dsn) as connection:
        connection.execute(seed)
        results = []
        for statement in [part for part in queries.split(";\n") if part.strip() and "SELECT" in part]:
            results.append(connection.execute(statement).fetchall())
    deployments, trace, table = results
    assert [row[1] for row in deployments] == ["d1", "d2", "d3", "d4"]
    assert trace[0][0] == "a5"
    assert float(trace[0][4]) == 66.0
    assert [tuple(float(value) for value in row[1:]) for row in table] == [
        (1.0, 62.0, 100.0, 240.0),
        (4.0, 4.0, 25.0, 30.0),
    ]


def test_the_deployments_view_lists_every_deployment_with_its_commits_and_an_empty_one(store, settings):
    store.append(
        [
            Event(NOW, "it-orders", EventType.DEPLOY, "d1:a1+a2"),
            Event(NOW, "it-orders", EventType.DEPLOY, "d2:"),
        ]
    )
    with psycopg.connect(settings.dsn) as connection:
        rows = connection.execute(
            "SELECT deploy_id, commit_ref FROM deploy_commits WHERE service = 'it-orders' "
            "ORDER BY deploy_id, commit_ref"
        ).fetchall()
    assert rows == [("d1", "a1"), ("d1", "a2"), ("d2", None)]


def test_the_cli_prints_the_sample_table_from_the_csv_without_a_database():
    done = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "goldenpath"), "metrics", "--csv", str(ROOT / "data" / "events-sample.csv")],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = {line.split()[0]: line.split() for line in done.stdout.splitlines()[1:]}
    assert lines["orders"][1:7] == ["4", "4.0", "h", "25%", "30", "min"]
    assert lines["billing"][1:7] == ["1", "62.0", "h", "100%", "240", "min"]
