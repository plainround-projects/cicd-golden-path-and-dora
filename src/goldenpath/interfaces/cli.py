"""`goldenpath`: generate a service, audit it, record events, compute the DORA metrics, trace a value."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from goldenpath.application import measure
from goldenpath.application.generate_service import NonConformingServiceError, ServiceGenerator
from goldenpath.application.ports import EventStore
from goldenpath.application.record_events import list_deployments, record
from goldenpath.domain import simulation
from goldenpath.domain.errors import DomainError
from goldenpath.domain.events import Event, EventType, parse_timestamp
from goldenpath.domain.rules import summarize
from goldenpath.infrastructure import local_pipeline
from goldenpath.infrastructure.auditor import RepositoryAuditor
from goldenpath.infrastructure.catalog_files import FileCatalog
from goldenpath.infrastructure.collector_client import CollectorError, CollectorEventSink
from goldenpath.infrastructure.csv_store import CsvEventStore
from goldenpath.infrastructure.logging import configure_logging, fields
from goldenpath.infrastructure.postgres_store import PostgresEventStore
from goldenpath.infrastructure.repositories import GitRepositories, commits_since
from goldenpath.infrastructure.settings import ConfigurationError, Settings
from goldenpath.infrastructure.template_renderer import FileTemplateRenderer
from goldenpath.interfaces.collector import collector_server
from goldenpath.interfaces.render import metrics_table

_log = logging.getLogger("goldenpath")
ROOT = Path(__file__).resolve().parents[3]

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    """The argument parser; exposed so tests can drive it."""
    parser = argparse.ArgumentParser(prog="goldenpath", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new-service", help="create a service from the golden path")
    new.add_argument("name")
    new.add_argument("owner", help="the owning team, for example team-orders")
    new.add_argument(
        "--release", action="store_true", help="also run its pipeline: image, sign, attest, verify, deploy"
    )
    audit = commands.add_parser("audit", help="check a repository against the golden-path contract")
    audit.add_argument("path", type=Path)
    emit = commands.add_parser("emit", help="send one delivery event to the collector")
    emit.add_argument("type", choices=[kind.value for kind in EventType])
    emit.add_argument("service")
    emit.add_argument("ref")
    emit.add_argument("--detail", default="")
    emit.add_argument("--ts", help="event time (ISO 8601); the collector's clock when omitted")
    emit.add_argument("--direct", action="store_true", help="write to the database instead of through the collector")
    commands.add_parser("collector", help="run the event collector (POST /events)")
    sim = commands.add_parser("simulate", help="replace the stored events with a simulated month for three teams")
    sim.add_argument("--seed", type=int, default=7)
    sim.add_argument("--days", type=int, default=28)
    metrics = commands.add_parser("metrics", help="the four DORA metrics per service")
    metrics.add_argument("--csv", type=Path, help="read events from a CSV file instead of the database")
    metrics.add_argument("--weekly", action="store_true", help="one table per week")
    trace = commands.add_parser("trace", help="trace one lead time back to its commit and deployment events")
    trace.add_argument("service")
    trace.add_argument("commit")
    trace.add_argument("--csv", type=Path)
    deployments = commands.add_parser("deployments", help="every production deployment of a service with its commits")
    deployments.add_argument("service")
    deployments.add_argument("--csv", type=Path)
    commands.add_parser("catalog", help="list the registered services")
    unsigned = commands.add_parser("demo-unsigned", help="push an unsigned image of a service and try to deploy it")
    unsigned.add_argument("name")
    return parser


def _store(settings: Settings, csv_path: Path | None = None) -> EventStore:
    return CsvEventStore(csv_path) if csv_path else PostgresEventStore(settings.dsn)


def _catalog(settings: Settings) -> FileCatalog:
    return FileCatalog(ROOT / "catalog" / "teams.yaml", settings.workdir / "catalog" / "entities")


def _platform_ref() -> str:
    done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S607
    return done.stdout.strip() or "0" * 40


def _pipeline_env(settings: Settings) -> dict[str, str]:
    keys = (settings.workdir / "keys").resolve()
    return {
        "REGISTRY": os.environ.get("REGISTRY", "localhost:55061"),
        "COSIGN_KEY": str(keys / "cosign.key"),
        "COSIGN_PUBLIC_KEY": str(keys / "cosign.pub"),
        "COSIGN_PASSWORD": os.environ.get("COSIGN_PASSWORD", ""),
        "EVENTS_URL": settings.collector_url,
        "EVENTS_TOKEN": settings.collector_token,
    }


def _new_service(args: argparse.Namespace, settings: Settings) -> int:
    started = time.monotonic()
    destination = (settings.workdir / "services" / args.name).resolve()
    catalog = _catalog(settings)
    generator = ServiceGenerator(
        FileTemplateRenderer(ROOT / "template"),
        catalog,
        GitRepositories((settings.workdir / "remotes").resolve()),
        RepositoryAuditor(catalog),
        _platform_ref(),
    )
    try:
        service = generator.generate(args.name, args.owner, destination, settings.runbook_base)
    except NonConformingServiceError as error:
        print(summarize(error.findings), file=sys.stderr)
        return EXIT_FAILED
    entry = service.entry
    print(f"created {entry.name} (owner {entry.owner}) at {service.directory}, commit {service.commit[:7]}")
    print(f"  catalog entry registered; generated {len(service.files)} files; audit: {summarize([])}")
    if not args.release:
        return EXIT_OK
    return _release(args.name, destination, settings, started)


def _release(name: str, directory: Path, settings: Settings, started: float) -> int:
    env = _pipeline_env(settings)
    sink = CollectorEventSink(settings.collector_url, settings.collector_token)
    commits = list(commits_since(directory, None))
    record(sink, [Event(datetime.now(tz=simulation.START.tzinfo), name, EventType.COMMIT, ref) for ref in commits])
    deployment = f"{name}-d1"
    env |= {"SERVICE_NAME": name}
    steps = ("lint", "test", "image", "sign", "attest", "verify", "deploy")
    variables = {"deploy": [f"COMMITS={'+'.join(commits)}", f"DEPLOYMENT={deployment}"]}
    try:
        results = local_pipeline.run_steps(directory, steps, env, variables)
    except local_pipeline.StepFailedError as error:
        print(error, file=sys.stderr)
        return EXIT_FAILED
    for result in results:
        print(f"  {result.name:<7}{result.seconds:6.1f}s")
    total = time.monotonic() - started
    print(f"{name}: from the command to the first production deployment in {total:.0f}s (limit: 1800s)")
    return EXIT_OK


def _demo_unsigned(name: str, settings: Settings) -> int:
    directory = (settings.workdir / "services" / name).resolve()
    env = _pipeline_env(settings) | {"SERVICE_NAME": name}
    image = local_pipeline.build_unsigned_image(directory, env["REGISTRY"], name, "unsigned", env)
    print(f"pushed by hand, never signed: {image}")
    status, output = local_pipeline.try_deploy(directory, name, image, f"{name}-d-unsigned", env)
    for line in output.splitlines():
        if "no signatures found" in line or "deploy refused" in line:
            print(line.strip())
    print(f"deploy exit status: {status} ({'refused' if status else 'ACCEPTED: the contract is broken'})")
    return EXIT_OK if status != 0 else EXIT_FAILED


def _serve_collector(settings: Settings) -> int:
    if not settings.collector_token:
        print("configuration error: COLLECTOR_TOKEN must be set", file=sys.stderr)
        return EXIT_USAGE
    server = collector_server(settings.collector_port, PostgresEventStore(settings.dsn), settings.collector_token)
    stop = threading.Event()

    def request_stop(signum: int, frame: object) -> None:
        _log.info("shutdown requested", extra=fields(signal=signal.Signals(signum).name))
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _log.info("collecting", extra=fields(port=settings.collector_port))
    stop.wait()
    server.shutdown()
    server.server_close()
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the exit code instead of exiting, so tests can call it."""
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env(
            need_database=args.command in {"collector", "simulate", "metrics", "trace", "deployments"}
            and not getattr(args, "csv", None)
        )
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return EXIT_USAGE
    configure_logging(settings.log_level)
    try:
        return _dispatch(args, settings)
    except (DomainError, CollectorError, measure.NoEventsError, local_pipeline.StepFailedError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_USAGE if isinstance(error, DomainError) else EXIT_FAILED
    except Exception:
        _log.exception("command failed", extra=fields(command=args.command))
        return EXIT_FAILED


def _dispatch(args: argparse.Namespace, settings: Settings) -> int:
    match args.command:
        case "new-service":
            return _new_service(args, settings)
        case "audit":
            from goldenpath.infrastructure.auditor import RepositoryAuditor as Auditor

            findings = Auditor(_catalog(settings)).audit(args.path)
            print(summarize(findings))
            return EXIT_FAILED if findings else EXIT_OK
        case "emit":
            when = parse_timestamp(args.ts) if args.ts else datetime.now(tz=simulation.START.tzinfo)
            event = Event(when, args.service, EventType(args.type), args.ref, args.detail)
            sink = (
                PostgresEventStore(settings.dsn)
                if args.direct
                else CollectorEventSink(settings.collector_url, settings.collector_token)
            )
            print(f"recorded {event.type.value} {event.ref}: {record(sink, [event])} new")
            return EXIT_OK
        case "collector":
            return _serve_collector(settings)
        case "simulate":
            store = PostgresEventStore(settings.dsn)
            events = simulation.simulate(args.seed, args.days)
            store.clear()
            teams = len({event.service for event in events})
            recorded = record(store, events)
            summary = f"{len(events)} events for {teams} teams over {args.days} days (seed {args.seed})"
            print(f"simulated {summary}: {recorded} recorded")
            return EXIT_OK
        case "metrics":
            reader = _store(settings, args.csv)
            if args.weekly:
                for index, rows in measure.per_week(reader):
                    print(f"\nweek {index}\n{metrics_table(rows, weekly=True)}")
            else:
                print(metrics_table(measure.summary(reader)))
            return EXIT_OK
        case "trace":
            lead = measure.trace(_store(settings, args.csv), args.service, args.commit)
            print(f"commit event:  {lead.commit.ts:%Y-%m-%d %H:%M}  {lead.commit.service}  commit  {lead.commit.ref}")
            print(f"deploy event:  {lead.deploy.ts:%Y-%m-%d %H:%M}  {lead.deploy.service}  deploy  {lead.deploy.ref}")
            print(f"lead time:     {lead.hours:.1f} h")
            return EXIT_OK
        case "deployments":
            for stamp, deployment, commits in list_deployments(_store(settings, args.csv), args.service):
                print(f"{stamp}  {deployment}  commits: {', '.join(commits) or '(none)'}")
            return EXIT_OK
        case "catalog":
            for entry in _catalog(settings).entries():
                print(f"{entry.name:<20}{entry.owner:<16}{entry.lifecycle:<12}{entry.runbook}")
            return EXIT_OK
        case "demo-unsigned":
            return _demo_unsigned(args.name, settings)
    return EXIT_OK
