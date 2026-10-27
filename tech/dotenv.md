# Environment variables and the `.env` file

## What it is

When you start a program in a terminal, the shell hands it a small set of named pieces of text called **environment variables**. A variable has a name (by convention in capitals, such as `POSTGRES_PORT`) and a value (text, such as `55471`). Every program can read its own environment: in Python, `os.environ["POSTGRES_PORT"]`. A program that is started by another program receives a *copy* of its parent's variables, and it can change only its own copy.

You set a variable for one command like this: `LOG_LEVEL=DEBUG some-command`. Or for everything the shell starts afterwards: `export LOG_LEVEL=DEBUG`.

A **`.env` file** is a plain text file with one `NAME=value` per line. It is only a *convention*: the operating system does not know about it. Some program has to read the file and set the variables. Here the reader is `make` ([make.md](make.md)) and, for its own substitutions, Docker Compose ([docker-compose.md](docker-compose.md)).

## Why this repository uses it

The platform follows the twelve-factor rule: configuration comes from the environment, not from values written in code. The same code runs on a laptop, in CI and in containers; only the variables change. **Passwords and tokens have no default**: a missing database password stops the program at start-up, and the collector refuses to start without its token.

## Where it appears

| Path | Role |
|---|---|
| `.env.example` | Committed template with throw-away local values. `make up` copies it to `.env`. |
| `.env` | Your local copy; ignored by Git. |
| `Makefile` lines 9 to 11 | `-include .env` and `export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL COLLECTOR_PORT COLLECTOR_URL COLLECTOR_TOKEN REGISTRY RUNBOOK_BASE COSIGN_PASSWORD`. |
| `docker-compose.yml` | Fills `${POSTGRES_PORT:-55441}`, `${REGISTRY_PORT:-55061}` and the password. |
| `src/goldenpath/infrastructure/settings.py` | Reads and validates them. |
| `template/scripts/*.sh` | Read `EVENTS_URL`, `EVENTS_TOKEN`, `SERVICE_NAME`, `COSIGN_PUBLIC_KEY`, `GITHUB_REPOSITORY`. |
| `src/goldenpath/interfaces/cli.py` | `_pipeline_env` builds the environment of a generated service's pipeline. |

## How it works underneath

Every process has an environment; the operating system copies it to each child. All values are text, so a program must convert `"55471"` into the number 55471 itself and decide what to do if the text is not a number. A `.env` file never reaches a program unless a reader loads it and exports its contents. `make` can read a `.env` file directly because a line `POSTGRES_PORT=55471` is also a valid `make` assignment; `export` then passes the named variables to every command that `make` starts.

## Walkthrough of this repository's use

### The variables

The variable names appear in `Makefile` lines 10 and 11 and in `Settings`:

- `POSTGRES_HOST` (default `localhost`), `POSTGRES_PORT` (default 5432 in the program; the example file sets the published port 55441), `POSTGRES_DB` (default `events`), `POSTGRES_USER` (default `platform`) and `POSTGRES_PASSWORD` (no default): the database.
- `LOG_LEVEL` (default `INFO`). `COLLECTOR_PORT` (default 55442), `COLLECTOR_URL` (default `http://127.0.0.1:<port>`) and `COLLECTOR_TOKEN` (no default): the event collector.
- `GOLDENPATH_WORKDIR` (default `.local`): where generated services, remotes, keys and logs are kept. `RUNBOOK_BASE` (default `https://wiki.example.com/runbooks`): the base of every service's runbook link.
- `REGISTRY` (default `localhost:55061`) and `COSIGN_PASSWORD`: the image registry and the password of the demo signing key ([cosign.md](cosign.md)).

### How `make` hands them over

`-include .env` makes `make` read the file (a line `POSTGRES_PORT=55441` is also a valid `make` assignment), and `export` marks eleven names for passing to every command `make` starts. `.env:` is a rule that runs `cp .env.example .env` when the file is missing ([make.md](make.md)).

### `Settings.from_env`

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- `_text(environ, name, default)` reads a variable, removes surrounding spaces and raises `ConfigurationError("NAME must be set and not empty")` if the result is empty. `_port(environ, name, default)` accepts only digits and a number from 1 to 65535 (`raw.isdigit()`, `1 <= int(raw) <= 65535`).

<!-- fmt:off -->
```python
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
```
<!-- fmt:on -->

- **Lines 50 to 53**: `from_env(cls, environ=None, need_database=True)` is a class method; with `environ=None` it uses the real environment (tests pass a dictionary).
- **Lines 54 to 62**: the host is checked with a pattern; the log level is upper-cased and must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`; `collector_port = _port(env, "COLLECTOR_PORT", 55442)`.
- **Lines 63 to 77**: the object is built. `postgres_password=_text(env, "POSTGRES_PASSWORD") if need_database else env.get("POSTGRES_PASSWORD", "")`: the password is required only for commands that touch the database (`collector`, `simulate`, `metrics`, `trace`, `deployments`, unless `--csv` is given), so `new-service` and `audit` run with no database settings. `collector_token=env.get("COLLECTOR_TOKEN", "").strip()` has no default. `workdir=Path(_text(env, "GOLDENPATH_WORKDIR", ".local"))`.
- **Lines 79 to 81**: the `dsn` property: `postgresql://` + the user and password (each passed through `quote(x, safe='')` so characters such as `@` or `/` cannot break the URL) + `@host:port/` + the database name. Never log it: it holds the password.
- `main()` in `cli.py` catches `ConfigurationError`, prints `configuration error: ...` and returns exit code 2. For the collector, `_serve_collector` checks `settings.collector_token` itself and prints `configuration error: COLLECTOR_TOKEN must be set`.

### A generated service's environment: `_pipeline_env`

<!-- fmt:off -->
```python

def _pipeline_env(settings: Settings) -> dict[str, str]:
    keys = (settings.workdir / "keys").resolve()
    return {
        "REGISTRY": os.environ.get("REGISTRY", "localhost:55061"),
        "COSIGN_KEY": str(keys / "cosign.key"),
        "COSIGN_PUBLIC_KEY": str(keys / "cosign.pub"),
        "COSIGN_PASSWORD": os.environ.get("COSIGN_PASSWORD", ""),
        "EVENTS_URL": settings.collector_url,
        "EVENTS_TOKEN": settings.collector_token,
```
<!-- fmt:on -->

Builds the dictionary handed to the generated service's `make` steps: `REGISTRY`, the paths of `cosign.key` and `cosign.pub`, `COSIGN_PASSWORD`, `EVENTS_URL` (the collector's address) and `EVENTS_TOKEN`. `_release` adds `SERVICE_NAME` (`env |= {"SERVICE_NAME": name}`; `|=` merges a dictionary into another). The template's Makefile exports `EVENTS_URL`, `SERVICE_NAME` and `COSIGN_PUBLIC_KEY` to the scripts ([bash-and-sh.md](bash-and-sh.md)).

## Try it yourself

```bash
make -B .env && grep -c "=" .env
```
`-B` forces the copy rule. Counts the lines of settings.

```bash
(unset POSTGRES_PASSWORD COLLECTOR_TOKEN; .venv/bin/goldenpath collector; echo "exit: $?")
```
Expect `configuration error: POSTGRES_PASSWORD must be set and not empty` and `exit: 2`.

```bash
POSTGRES_PASSWORD=x LOG_LEVEL=LOUD .venv/bin/goldenpath catalog; echo "exit: $?"
```
Expect `configuration error: LOG_LEVEL must be one of ['DEBUG', 'ERROR', 'INFO', 'WARNING'], got 'LOUD'` and `exit: 2`.

```bash
(unset POSTGRES_PASSWORD; .venv/bin/goldenpath catalog; echo "exit: $?")
```
Works without a database password and prints the registered services (or nothing).

## Mistakes people make

- Committing `.env`. It is in `.gitignore`.
- Defaults for secrets "to make it work".
- Reading the environment all over the code.
- Logging the DSN.
- Spaces around `=` in a `.env` file.

## Check yourself

1. What is an environment variable? *Named text a process receives from its parent.*
2. Why is there no default token? *A missing secret should fail loudly.*
3. Which commands need the database password? *Those that read or write the store.*
4. Why quote the parts of the DSN? *So special characters cannot break the URL.*
5. Who reads `.env`? *Make and Docker Compose, not Python.*

## Further reading

- The Twelve-Factor App, config: https://12factor.net/config
- Compose environment files: https://docs.docker.com/compose/how-tos/environment-variables/
- `urllib.parse.quote`: https://docs.python.org/3.12/library/urllib.parse.html#urllib.parse.quote
