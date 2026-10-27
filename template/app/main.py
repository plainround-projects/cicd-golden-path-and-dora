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
