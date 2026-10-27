import io
import json
import logging
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from goldenpath.domain.catalog import CatalogEntry
from goldenpath.domain.events import Event, EventType
from goldenpath.infrastructure.auditor import RepositoryAuditor, load_workflow, read_text_files
from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.collector_client import CollectorError, CollectorEventSink
from goldenpath.infrastructure.csv_store import CsvEventStore
from goldenpath.infrastructure.logging import LogfmtFormatter, configure_logging, fields
from goldenpath.infrastructure.settings import ConfigurationError, Settings
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer
from goldenpath.interfaces.collector import collector_server, event_from_json
from goldenpath.interfaces.render import metrics_table

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def test_the_csv_store_round_trips_events_and_ignores_a_duplicate(tmp_path):
    store = CsvEventStore(tmp_path / "events.csv")
    events = [Event(NOW, "orders", EventType.COMMIT, "a1"), Event(NOW, "orders", EventType.FAILED, "d1", "rollback")]
    assert store.append(events) == 2
    assert store.append(events) == 0
    assert store.all() == events
    store.clear()
    assert store.all() == []


def test_the_csv_store_reads_the_lessons_four_column_sample():
    events = CsvEventStore(ROOT / "data" / "events-sample.csv").all()
    assert len(events) == 18
    assert events[0] == Event(datetime(2026, 9, 1, 9, 0, tzinfo=UTC), "orders", EventType.COMMIT, "a1")


def test_settings_have_defaults_and_the_password_has_none():
    settings = Settings.from_env({"POSTGRES_PASSWORD": "pw"})
    assert (settings.postgres_port, settings.collector_port, settings.workdir) == (5432, 55442, Path(".local"))
    with pytest.raises(ConfigurationError, match="POSTGRES_PASSWORD"):
        Settings.from_env({})
    assert Settings.from_env({}, need_database=False).postgres_password == ""


@pytest.mark.parametrize(
    ("name", "value"),
    [("POSTGRES_PORT", "0"), ("COLLECTOR_PORT", "abc"), ("POSTGRES_HOST", "a b"), ("LOG_LEVEL", "LOUD")],
)
def test_an_unusable_setting_names_its_variable(name, value):
    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env({"POSTGRES_PASSWORD": "pw", name: value})


def test_the_connection_uri_escapes_the_password():
    assert (
        Settings.from_env({"POSTGRES_PASSWORD": "p@ss/w"}).dsn
        == "postgresql://platform:p%40ss%2Fw@localhost:5432/events"
    )


def test_a_log_record_is_one_logfmt_line_and_the_stream_gets_it():
    record = logging.LogRecord("goldenpath", logging.INFO, __file__, 1, "two words", None, None)
    record.fields = {"service": "orders"}
    assert LogfmtFormatter().format(record).endswith('msg="two words" service=orders')
    stream = io.StringIO()
    configure_logging("INFO", stream)
    logging.getLogger("x").info("hi", extra=fields(a=1))
    assert "msg=hi a=1" in stream.getvalue()


def test_rendering_replaces_every_placeholder_and_keeps_scripts_executable(tmp_path):
    destination = tmp_path / "orders"
    written = FileTemplateRenderer(ROOT / "template").render(
        destination,
        {"__NAME__": "orders", "__OWNER__": "team-orders", "__RUNBOOK__": "https://x/r", "__PLATFORM_REF__": "f" * 40},
    )
    assert "Makefile" in written
    assert "orders" in (destination / "catalog-info.yaml").read_text()
    assert not any("__NAME__" in text for text in read_text_files(destination).values())
    assert (destination / "scripts" / "deploy.sh").stat().st_mode & 0o111


def test_rendering_into_an_existing_folder_is_refused(tmp_path):
    with pytest.raises(FileExistsError):
        FileTemplateRenderer(ROOT / "template").render(tmp_path, {})


def render(tmp_path: Path, name: str = "orders", owner: str = "team-orders") -> Path:
    destination = tmp_path / name
    FileTemplateRenderer(ROOT / "template").render(
        destination,
        {
            "__NAME__": name,
            "__OWNER__": owner,
            "__RUNBOOK__": "https://wiki.example.com/r",
            "__PLATFORM_REF__": "f" * 40,
        },
    )
    return destination


def auditor() -> RepositoryAuditor:
    return RepositoryAuditor(FileCatalog(ROOT / "catalog" / "teams.yaml", Path("/nonexistent")))


def test_a_freshly_generated_repository_conforms(tmp_path):
    assert auditor().audit(render(tmp_path)) == []


def test_a_repository_whose_signing_step_was_deleted_fails_the_audit(tmp_path):
    repo = render(tmp_path)
    workflow = repo / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text().replace("      - run: make sign\n", ""))
    assert "GP-SIGN" in {finding.code for finding in auditor().audit(repo)}


def test_a_stored_cloud_key_in_the_repository_fails_the_audit(tmp_path):
    repo = render(tmp_path)
    (repo / "deploy" / "creds.env").write_text("AWS_KEY=AKIAABCDEFGHIJKLMNOP\n")
    assert "GP-SECRET" in {finding.code for finding in auditor().audit(repo)}


def test_a_person_as_owner_fails_the_audit_through_the_catalog_entry(tmp_path):
    repo = render(tmp_path, owner="alice")
    assert "GP-CATALOG" in {finding.code for finding in auditor().audit(repo)}


def test_missing_protection_and_catalog_files_are_findings(tmp_path):
    repo = render(tmp_path)
    (repo / "protection.json").unlink()
    (repo / "catalog-info.yaml").unlink()
    codes = {finding.code for finding in auditor().audit(repo)}
    assert {"GP-CHECKS", "GP-CATALOG"} <= codes


def test_a_repository_with_no_workflow_is_a_finding(tmp_path):
    repo = render(tmp_path)
    (repo / ".github" / "workflows" / "ci.yml").unlink()
    assert "GP-NOWORKFLOW" in {finding.code for finding in auditor().audit(repo)}


def test_the_workflow_loader_puts_the_on_key_back():
    assert "push" in load_workflow("on:\n  push:\njobs: {}\n")["on"]
    with pytest.raises(ValueError, match="mapping"):
        load_workflow("- a\n")


def test_the_catalog_registers_replaces_and_lists_entries(tmp_path):
    catalog = FileCatalog(ROOT / "catalog" / "teams.yaml", tmp_path / "entities")
    assert catalog.entries() == []
    entry = CatalogEntry("orders", "team-orders", "production", "https://x/r", "99.9%")
    catalog.register(entry)
    catalog.register(CatalogEntry("orders", "team-orders", "deprecated", "https://x/r", "99.9%"))
    assert [item.lifecycle for item in catalog.entries()] == ["deprecated"]
    assert "team-platform" in catalog.teams()


def test_the_metrics_table_prints_n_a_for_what_has_no_value():
    from goldenpath.domain import metrics

    events = [Event(NOW, "quiet", EventType.COMMIT, "q1")]
    start, end = metrics.window_of(events)
    table = metrics_table([metrics.compute(events, "quiet", start, end)])
    assert "quiet" in table
    assert table.count("n/a") == 4


def test_an_event_from_json_defaults_to_the_collectors_clock_and_refuses_a_bad_type():
    event = event_from_json({"service": "orders", "type": "commit", "ref": "a1"}, NOW)
    assert event.ts == NOW
    with pytest.raises(Exception, match="type"):
        event_from_json({"service": "orders", "type": "teleport", "ref": "a1"}, NOW)


@pytest.fixture
def collector(tmp_path: Path) -> Iterator[tuple[str, CsvEventStore]]:
    store = CsvEventStore(tmp_path / "events.csv")
    server = collector_server(0, store, "secret-token", clock=lambda: NOW)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", store
    server.shutdown()
    server.server_close()


def post(url: str, body: bytes, token: str | None = "secret-token") -> tuple[int, dict[str, object]]:
    headers = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url + "/events", data=body, headers=headers, method="POST")
        ) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_the_collector_accepts_an_authorized_event_and_stores_it_once(collector):
    url, store = collector
    body = json.dumps({"service": "orders", "type": "commit", "ref": "a1"}).encode()
    assert post(url, body) == (202, {"accepted": 1, "received": 1})
    assert post(url, body) == (202, {"accepted": 0, "received": 1})
    assert store.all() == [Event(NOW, "orders", EventType.COMMIT, "a1")]


def test_the_collector_refuses_a_missing_or_wrong_token(collector):
    url, store = collector
    body = json.dumps({"service": "orders", "type": "commit", "ref": "a1"}).encode()
    assert post(url, body, token=None)[0] == 401
    assert post(url, body, token="wrong")[0] == 401
    assert store.all() == []


@pytest.mark.parametrize(
    "body", [b"not json", b"[]{", json.dumps({"service": "X", "type": "commit", "ref": "a1"}).encode(), b"{}"]
)
def test_the_collector_refuses_a_malformed_or_invalid_event(collector, body):
    assert post(collector[0], body)[0] == 400


def test_the_collector_refuses_an_empty_or_oversized_body_and_unknown_paths(collector):
    url, _ = collector
    assert post(url, b"")[0] == 400
    assert post(url, b"x" * (64 * 1024 + 1))[0] == 413
    assert urllib.request.urlopen(url + "/healthz").status == 200
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url + "/nope")


def test_the_client_sends_a_batch_and_reads_how_many_were_new(collector):
    url, store = collector
    sink = CollectorEventSink(url, "secret-token")
    assert (
        sink.append([Event(NOW, "orders", EventType.COMMIT, "a1"), Event(NOW, "orders", EventType.DEPLOY, "d1:a1")])
        == 2
    )
    assert len(store.all()) == 2


def test_the_client_reports_a_refusal_and_an_unreachable_collector(collector):
    url, _ = collector
    with pytest.raises(CollectorError, match="401"):
        CollectorEventSink(url, "wrong").append([Event(NOW, "orders", EventType.COMMIT, "a1")])
    with pytest.raises(CollectorError, match="could not be reached"):
        CollectorEventSink("http://127.0.0.1:1", "t", timeout_seconds=0.5).append(
            [Event(NOW, "orders", EventType.COMMIT, "a1")]
        )
    with pytest.raises(ValueError, match="http"):
        CollectorEventSink("file:///x", "t")


def test_a_collector_with_no_token_configured_refuses_everything(tmp_path):
    server = collector_server(0, CsvEventStore(tmp_path / "e.csv"), "")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert post(f"http://127.0.0.1:{server.server_address[1]}", b"{}", token="")[0] == 401
    finally:
        server.shutdown()
        server.server_close()
