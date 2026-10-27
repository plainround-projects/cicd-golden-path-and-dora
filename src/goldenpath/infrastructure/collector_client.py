"""The pipeline's side of event recording: POST events to the collector with a bearer token."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterable

from goldenpath.domain.events import Event


class CollectorError(RuntimeError):
    """The collector refused or could not be reached."""


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
