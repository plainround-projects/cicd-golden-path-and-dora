# HTTP and Python's `http.server`

## What it is

**HTTP** is the text conversation between a client and a server ([curl.md](curl.md) explains requests, methods, headers, bodies and status codes). A **server** is a program that keeps running, listens on a **port** (a numbered door, 1 to 65535, on a computer), and answers each request that arrives. The address `127.0.0.1` means "this very computer"; a server that listens only there cannot be reached from other machines. `0.0.0.0` means "every network interface".

Python's standard library includes a small HTTP server. `BaseHTTPRequestHandler` is the class whose methods answer one request: you write `do_GET` for GET requests and `do_POST` for POST requests. `ThreadingHTTPServer((host, port), HandlerClass)` listens and starts a **thread** (a line of execution that runs alongside others) for each request, so a slow request does not block the rest.

## Why this repository uses it

Two small servers exist. The **collector** receives delivery events from pipelines (`POST /events`) and stores them. The **generated service** answers `/healthz` and `/`. Using only the standard library keeps the generated service free of dependencies and the platform's list of installed packages short.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/interfaces/collector.py` | The collector: `GET /healthz`, `POST /events`. |
| `src/goldenpath/infrastructure/collector_client.py` | The matching client, built on `urllib.request`. |
| `template/app/main.py` | The generated service: `/healthz` and `/`. |
| `docs/adr/0004-a-collector-in-front-of-the-event-store.md` | Why a collector sits in front of the database. |

## How it works underneath

The server accepts a network connection, reads the request line (`POST /events HTTP/1.1`) and the headers, and hands them to a new handler object, which calls `do_GET` or `do_POST`. Inside the handler: `self.path` is the address path; `self.headers` holds the request headers; `self.rfile` is a stream from which the body is read (exactly `Content-Length` bytes); `self.send_response(code)`, `self.send_header(name, value)`, `self.end_headers()` and `self.wfile.write(bytes)` send the reply. `serve_forever()` loops until `shutdown()` is called from another thread.

A **bearer token** is a secret string sent in the header `Authorization: Bearer <token>`; the server grants access to whoever presents it. Comparing secrets with `==` can leak, through timing, how many leading characters were right, so a constant-time comparison (`hmac.compare_digest`) is used.

## Walkthrough of this repository's use

### The collector, `src/goldenpath/interfaces/collector.py`

<!-- fmt:off -->
```python
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

```
<!-- fmt:on -->

- **Line 1**: the docstring: `POST /events` from pipelines and `GET /healthz`, in front of the event store. **Lines 5 to 15**: imports (`hmac`, `json`, `Mapping`, time types, the server classes, `Any`, the ports and domain types). **Line 17**: `MAX_BODY_BYTES = 64 * 1024`: the largest request body accepted, 64 kibibytes.

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 20 to 29**, `event_from_json(item, now)`: turns a JSON object into a validated `Event`. `kind = EventType(str(item["type"]))`, `service = str(item["service"])`, `ref = str(item["ref"])` in a `try:` block; if a key is missing (`KeyError`) or the type is not one of the four (`ValueError`), `raise InvalidEventError("an event needs type (commit, deploy, failed or recovered), service and ref") from None`. `ts = parse_timestamp(str(item["ts"])) if item.get("ts") else now`: **a missing time means "now" on the collector's clock**, so a pipeline cannot choose its own timestamp. `str(item.get("detail") or "")` takes the optional reason.
- **Lines 32 to 34**: `collector_server(port, sink, token, clock=None)` builds the server. `now = clock or (lambda: datetime.now(UTC))` uses the given clock or the real one (a `lambda` is a tiny nameless function).

<!-- fmt:off -->
```python
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

```
<!-- fmt:on -->

- **Line 36**: the handler class is defined *inside* the function so it can use `sink`, `token` and `now`.
- **Lines 37 to 43**, `_reply(status, payload)`: `body = (json.dumps(payload) + "\n").encode()` makes JSON text and encodes it to bytes; the headers say it is JSON and how many **bytes** it has (`len(body)`, which is why the text is encoded first); then the body is written.
- **Lines 45 to 47**, `_authorized`: `given = self.headers.get("Authorization", "")` reads the header (empty if missing); `bool(token) and hmac.compare_digest(given.encode(), f"Bearer {token}".encode())` is true only if a token is configured and the header equals `Bearer <token>`, compared in constant time. An empty configured token refuses everything.
- **Lines 49 to 53**, `do_GET`: `/healthz` answers `200 {"status": "ok"}`; any other path `404 {"error": "not found"}`.
- **Lines 55 to 61**, `do_POST`: a path other than `/events` is 404; without the right token it is `401 {"error": "a bearer token is required"}`; otherwise `_accept()`.

<!-- fmt:off -->
```python
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
            try:
                accepted = record(sink, events)
            except (
                Exception
            ):  # the store is down or slow: say so, so the pipeline step can retry; never crash the handler
                self._reply(503, {"error": "the event store is unavailable, try again"})
                return
            self._reply(202, {"accepted": accepted, "received": len(events)})

        def log_message(self, format: str, *args: Any) -> None:
            """Silence the default access log."""

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
```
<!-- fmt:on -->

- **Lines 64 to 67**: `length = int(self.headers.get("Content-Length", "0"))`; `if not 0 < length <= MAX_BODY_BYTES:` refuses a body that is empty (400) or too large (413: `413 if length else 400`). The limit stops a client from making the server read without end.
- **Lines 68 to 74**: `payload = json.loads(self.rfile.read(length))` reads exactly `length` bytes and parses the JSON; `items = payload if isinstance(payload, list) else [payload]` accepts one object or a list; `events = [event_from_json(item, now()) for item in items]` builds validated events. If the JSON is broken or an event is invalid, `except (json.JSONDecodeError, InvalidEventError, TypeError, AttributeError)` answers `400` with the message.
- **Lines 75 to 82**: `accepted = record(sink, events)` stores them. If *anything* fails there (`except Exception`, deliberately broad), the answer is `503 {"error": "the event store is unavailable, try again"}` so the pipeline step can retry; the handler never crashes. Success is `202` with `{"accepted": accepted, "received": len(events)}`: `accepted` is how many were new (a repeated event is stored once).
- **Lines 84 and 85**: `log_message` is overridden to do nothing; the default prints a line per request. **Line 87**: `ThreadingHTTPServer(("127.0.0.1", port), Handler)` listens on this computer only.

### The matching client, `collector_client.py`

<!-- fmt:off -->
```python
class CollectorEventSink:
    """An `EventSink` over HTTP. The token comes from the environment (`COLLECTOR_TOKEN`), never from code."""

    def __init__(self, url: str, token: str, timeout_seconds: float = 120.0) -> None:
        """`url` is the collector's base URL (http or https only)."""
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"url must start with http:// or https://, got {url!r}")
        self._url = url.rstrip("/")
        self._token = token
        self._timeout_seconds = timeout_seconds

    def append(self, events: Iterable[Event]) -> int:
        """Send events; return how many the collector accepted as new."""
        body = json.dumps(
            [
                {
                    "ts": event.ts.isoformat(),
                    "service": event.service,
                    "type": event.type.value,
                    "ref": event.ref,
                    "detail": event.detail,
                }
                for event in events
            ]
        ).encode()
        request = urllib.request.Request(  # noqa: S310 - scheme checked in __init__
            f"{self._url}/events",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                return int(json.loads(response.read())["accepted"])
        except urllib.error.HTTPError as error:
            raise CollectorError(
                f"the collector answered {error.code}: {error.read().decode(errors='replace').strip()}"
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CollectorError(f"the collector could not be reached at {self._url}: {error}") from None
```
<!-- fmt:on -->

- `CollectorEventSink.__init__` requires the URL to start with `http://` or `https://` and removes a trailing `/`. `append(events)` builds the JSON body, `urllib.request.Request(f"{self._url}/events", data=body, headers={...}, method="POST")`, and sends it with `urlopen(request, timeout=...)`; `int(json.loads(response.read())["accepted"])` is the reply's count. `urllib.error.HTTPError` (the server answered an error status) becomes `CollectorError("the collector answered 401: ...")`; `URLError`, `TimeoutError` or `OSError` (no answer) becomes `CollectorError("the collector could not be reached at ...")`. The `# noqa: S310` comments silence a lint warning about opening arbitrary URLs; the scheme check in `__init__` is the reason it is safe ([ruff.md](ruff.md)).

### The generated service, `template/app/main.py`

<!-- fmt:off -->
```python
"""__NAME__: a small HTTP service. Replace it with your own; keep /healthz."""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = os.environ.get("APP_VERSION", "dev")


def answer(path: str) -> tuple[int, str]:
    """The status and body for a path."""
    if path == "/healthz":
        return 200, "ok\n"
    if path == "/":
        return 200, json.dumps({"service": "__NAME__", "owner": "__OWNER__", "version": VERSION}) + "\n"
    return 404, "not found\n"


class Handler(BaseHTTPRequestHandler):
    """Serves `answer`."""

    def do_GET(self) -> None:
        status, body = answer(self.path)
        payload = body.encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """No access log."""


def main() -> None:
    """Serve on $PORT (default 8080)."""
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
```
<!-- fmt:on -->

- **Lines 3 to 5**: imports. **Line 7**: `VERSION = os.environ.get("APP_VERSION", "dev")` ([dotenv.md](dotenv.md)).
- **Lines 10 to 16**, `answer(path)`: all the logic, as a plain function returning `(status, body)`: `/healthz` gives `(200, "ok\n")`; `/` gives `(200, json.dumps({"service": "__NAME__", "owner": "__OWNER__", "version": VERSION}) + "\n")`; anything else `(404, "not found\n")`. `__NAME__` and `__OWNER__` are placeholders the platform replaces when it generates the service.
- **Lines 19 to 28**, `Handler.do_GET`: calls `answer(self.path)`, encodes the body (`body.encode()`), then `send_response(status)`, `send_header("Content-Length", str(len(payload)))`, `end_headers()` and `self.wfile.write(payload)`. **Lines 30 and 31**: `log_message` does nothing.
- **Lines 34 to 36**, `main`: `ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()` listens on every interface (so Docker can reach it from outside the container), on `PORT` or 8080. **Lines 39 and 40**: `if __name__ == "__main__": main()` runs it only when the file is started directly. The unit tests call `answer` without any network ([unittest-and-compileall.md](unittest-and-compileall.md)).

## Try it yourself

```bash
make up
curl -s http://127.0.0.1:55442/healthz
```
Expect `{"status": "ok"}`.

```bash
.venv/bin/python -c "
from goldenpath.interfaces.collector import event_from_json
from datetime import datetime, UTC
print(event_from_json({'type': 'commit', 'service': 'orders', 'ref': 'a1'}, datetime(2026,1,1,tzinfo=UTC)))
"
```
Prints an `Event` whose `ts` is the time passed in as `now`.

```bash
sed 's/__NAME__/demo/; s/__OWNER__/team-demo/' template/app/main.py > /tmp/demo_main.py
PORT=18080 python3 /tmp/demo_main.py & pid=$!
sleep 1; curl -s localhost:18080/healthz; curl -s localhost:18080/; kill $pid
```
Expect `ok` and `{"service": "demo", "owner": "team-demo", "version": "dev"}`. (`$!` is the process id of the last background command.)

## Mistakes people make

- Binding to `0.0.0.0` when only local access is needed (the generated service does bind to all interfaces inside its container; compose publishes it on `127.0.0.1` only).
- Reading a body of unlimited size.
- Comparing tokens with `==`.
- Letting an exception kill the handler thread without an answer.
- Trusting a caller-supplied time stamp.

## Check yourself

1. What does status 202 mean here? *The collector accepted the request and reports how many events were new.*
2. Why is `Content-Length` checked? *To bound how much is read from a possibly hostile client.*
3. What does an unavailable store return? *503, so the pipeline step can retry.*
4. Why `hmac.compare_digest`? *Constant-time comparison avoids leaking the token by timing.*
5. Why is `answer()` a separate function? *Tests can call it without a network.*

## Further reading

- `http.server`: https://docs.python.org/3.12/library/http.server.html
- HTTP semantics (RFC 9110): https://www.rfc-editor.org/rfc/rfc9110
- Status codes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status
