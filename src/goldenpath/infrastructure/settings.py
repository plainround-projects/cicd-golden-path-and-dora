"""Configuration from the environment, validated once at startup (twelve-factor)."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
_HOST = re.compile(r"^[\w.\-]+$")


class ConfigurationError(ValueError):
    """An environment variable is missing or has an unusable value."""


def _text(environ: Mapping[str, str], name: str, default: str | None = None) -> str:
    value = environ.get(name, default if default is not None else "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be set and not empty")
    return value


def _port(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name, str(default)).strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ConfigurationError(f"{name} must be a port number, got {raw!r}")
    return int(raw)


@dataclass(frozen=True, slots=True)
class Settings:
    """Everything the programs read from the environment. See .env.example for each variable."""

    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    log_level: str
    collector_port: int
    collector_url: str
    collector_token: str
    workdir: Path
    runbook_base: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None, need_database: bool = True) -> Settings:
        """Read and validate. Passwords and tokens have no default: they must come from the environment."""
        env = os.environ if environ is None else environ
        host = _text(env, "POSTGRES_HOST", "localhost")
        if not _HOST.match(host):
            raise ConfigurationError(f"POSTGRES_HOST must be a host name or address, got {host!r}")
        level = _text(env, "LOG_LEVEL", "INFO").upper()
        if level not in _LEVELS:
            raise ConfigurationError(f"LOG_LEVEL must be one of {sorted(_LEVELS)}, got {level!r}")
        collector_port = _port(env, "COLLECTOR_PORT", 55442)
        return cls(
            postgres_host=host,
            postgres_port=_port(env, "POSTGRES_PORT", 5432),
            postgres_db=_text(env, "POSTGRES_DB", "events"),
            postgres_user=_text(env, "POSTGRES_USER", "platform"),
            postgres_password=_text(env, "POSTGRES_PASSWORD") if need_database else env.get("POSTGRES_PASSWORD", ""),
            log_level=level,
            collector_port=collector_port,
            collector_url=_text(env, "COLLECTOR_URL", f"http://127.0.0.1:{collector_port}"),
            collector_token=env.get("COLLECTOR_TOKEN", "").strip(),
            workdir=Path(_text(env, "GOLDENPATH_WORKDIR", ".local")),
            runbook_base=_text(env, "RUNBOOK_BASE", "https://wiki.example.com/runbooks"),
        )

    @property
    def dsn(self) -> str:
        """A libpq connection URI. Never log this: it holds the password."""
        return (
            f"postgresql://{quote(self.postgres_user, safe='')}:{quote(self.postgres_password, safe='')}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote(self.postgres_db, safe='')}"
        )
