# HTTP and Python's `http.server`

## What it is

**HTTP** is the text protocol web services speak. A **client** sends a request: a method (`GET`, `POST`), a path (`/events`), headers (`Name: value`) and maybe a body. The **server** sends back a status code and a body. Status codes: 2xx success, 4xx the client was wrong, 5xx the server had a problem. Python's standard library contains a small HTTP server, `http.server`, built from `BaseHTTPRequestHandler` (the code that answers one request) and `ThreadingHTTPServer` (which handles each request on its own thread).

## Why this repository uses it

Two small servers exist. The **collector** receives delivery events from pipelines (`POST /events`) and puts them in the store. The **generated service** answers `/healthz` and `/`. Using only the standard library keeps the generated service free of dependencies and the platform's list of pinned packages short.

## Where it appears

| Path | Use |
|---|---|
| `src/goldenpath/interfaces/collector.py` | The collector: `GET /healthz`, `POST /events`. |
| `src/goldenpath/infrastructure/collector_client.py` | The matching client (`urllib.request`). |
| `template/app/main.py` | The generated service: `/healthz` and `/`. |
| `docs/adr/0004-a-collector-in-front-of-the-event-store.md` | Why a collector sits in front of the database. |

## How it works underneath

`ThreadingHTTPServer((host, port), Handler)` listens on a TCP port. For each connection it starts a thread that parses the request and calls `do_GET`, `do_POST` (and so on) on a new `Handler` object. The handler reads `self.path`, `self.headers` and `self.rfile` (the request body), and writes with `send_response`, `send_header`, `end_headers` and `self.wfile`. `serve_forever()` loops until `shutdown()` is called.

## Walkthrough of this repository's use

### The collector

```python
def collector_server(port: int, sink: EventSink, token: str, clock: Any = None) -> ThreadingHTTPServer:
    ...
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
```
The server listens on `127.0.0.1` only: other machines cannot reach it. It is given an `EventSink` (the store) and the expected token. The `Handler` class is defined inside the function so it can use `sink`, `token` and `now`.

```python
def _authorized(self) -> bool:
    given = self.headers.get("Authorization", "")
    return bool(token) and hmac.compare_digest(given.encode(), f"Bearer {token}".encode())
```
A write needs `Authorization: Bearer <token>`. `hmac.compare_digest` compares in constant time, so response time cannot leak how many characters matched. An empty configured token refuses everything.

```python
def do_POST(self) -> None:
    if self.path != "/events":
        self._reply(404, {"error": "not found"})
    elif not self._authorized():
        self._reply(401, {"error": "a bearer token is required"})
    else:
        self._accept()
```
Route, then authenticate, then act.

```python
length = int(self.headers.get("Content-Length", "0"))
if not 0 < length <= MAX_BODY_BYTES:
    self._reply(413 if length else 400, {"error": f"body must be 1 to {MAX_BODY_BYTES} bytes"})
    return
payload = json.loads(self.rfile.read(length))
items = payload if isinstance(payload, list) else [payload]
events = [event_from_json(item, now()) for item in items]
```
`Content-Length` says how many bytes to read from the request body, never more than 64 KiB. The body may be one JSON object or a list. `event_from_json` builds validated `Event` objects ([python.md](python.md)). **A missing `ts` means "now" on the collector's clock**: the pipeline cannot choose its own time stamp.

```python
try:
    accepted = record(sink, events)
except Exception:
    self._reply(503, {"error": "the event store is unavailable, try again"})
    return
self._reply(202, {"accepted": accepted, "received": len(events)})
```
If the store is down the collector answers `503` instead of crashing, so `curl` in the pipeline step fails and can be retried. `202 Accepted` reports how many events were new (a repeated event is stored once).

`log_message` is overridden with an empty body to silence the default access log.

### The client

`CollectorEventSink.append` builds the JSON list, creates a `urllib.request.Request(..., method="POST")` with the bearer header, and calls `urlopen(request, timeout=...)`. An `HTTPError` becomes `CollectorError("the collector answered 401: ...")`; a connection problem becomes `CollectorError("... could not be reached ...")`. The URL must start with `http://` or `https://`, checked in `__init__`, which is why the `S310` lint warning is silenced with a reason.

### The generated service

```python
def answer(path: str) -> tuple[int, str]:
    if path == "/healthz":
        return 200, "ok\n"
    ...
```
All logic is in a plain function (`answer`) that the unit tests call without any network; `Handler.do_GET` only turns its result into a response.

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
