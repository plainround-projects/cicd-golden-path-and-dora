"""The event collector: `POST /events` from pipelines and `GET /healthz`, in front of the event store."""

from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from goldenpath.application.ports import EventSink
from goldenpath.application.record_events import record
from goldenpath.domain.errors import InvalidEventError
from goldenpath.domain.events import Event, EventType, parse_timestamp

MAX_BODY_BYTES = 64 * 1024


def event_from_json(item: Mapping[str, Any], now: datetime) -> Event:
    """Build an event from a JSON object. A missing `ts` means "now" on the collector's clock."""
    try:
        kind = EventType(str(item["type"]))
        service = str(item["service"])
        ref = str(item["ref"])
    except (KeyError, ValueError):
        raise InvalidEventError("an event needs type (commit, deploy, failed or recovered), service and ref") from None
    ts = parse_timestamp(str(item["ts"])) if item.get("ts") else now
    return Event(ts, service, kind, ref, str(item.get("detail") or ""))


def collector_server(port: int, sink: EventSink, token: str, clock: Any = None) -> ThreadingHTTPServer:
    """A threaded server. Without the bearer token every write is refused; an empty `token` refuses everything."""
    now = clock or (lambda: datetime.now(UTC))

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: dict[str, object]) -> None:
            body = (json.dumps(payload) + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            given = self.headers.get("Authorization", "")
            return bool(token) and hmac.compare_digest(given.encode(), f"Bearer {token}".encode())

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._reply(200, {"status": "ok"})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/events":
                self._reply(404, {"error": "not found"})
            elif not self._authorized():
                self._reply(401, {"error": "a bearer token is required"})
            else:
                self._accept()

        def _accept(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                self._reply(413 if length else 400, {"error": f"body must be 1 to {MAX_BODY_BYTES} bytes"})
                return
            try:
                payload = json.loads(self.rfile.read(length))
                items = payload if isinstance(payload, list) else [payload]
                events = [event_from_json(item, now()) for item in items]
            except (json.JSONDecodeError, InvalidEventError, TypeError, AttributeError) as error:
                self._reply(400, {"error": str(error)})
                return
            self._reply(202, {"accepted": record(sink, events), "received": len(events)})

        def log_message(self, format: str, *args: Any) -> None:
            """Silence the default access log."""

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
