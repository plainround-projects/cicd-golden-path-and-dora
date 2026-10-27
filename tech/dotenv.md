# Environment variables and the `.env` file

## What it is

An **environment variable** is a named piece of text that a process receives from the program that started it (`COLLECTOR_PORT=55442`). A **`.env` file** is a plain text file of `NAME=value` lines that sets many of them at once in development. It is a convention: some tool has to read it (here Make, and Docker Compose for its `${...}` substitutions).

## Why this repository uses it

Configuration comes from the environment, not from values written in code ("twelve-factor"). The same code runs on a laptop and in CI; only the variables differ. **Passwords and tokens have no default:** a missing database password stops the program at startup.

## Where it appears

| Path | Role |
|---|---|
| `.env.example` | Committed template with throwaway local values; `make up` copies it to `.env`. |
| `.env` | Your local copy; ignored by git. |
| `Makefile` | `-include .env` and `export POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD LOG_LEVEL COLLECTOR_PORT COLLECTOR_URL COLLECTOR_TOKEN REGISTRY RUNBOOK_BASE COSIGN_PASSWORD`. |
| `docker-compose.yml` | Substitutes `${POSTGRES_PORT:-55441}`, `${REGISTRY_PORT:-55061}` and the password. |
| `src/goldenpath/infrastructure/settings.py` | Reads and validates them. |
| `template/scripts/*.sh` | Read `EVENTS_URL`, `EVENTS_TOKEN`, `SERVICE_NAME`, `COSIGN_PUBLIC_KEY`, `GITHUB_REPOSITORY`. |

## How it works underneath

A child process gets a **copy** of its parent's environment and cannot change the parent's. `export NAME` marks a shell variable to be passed on. Everything in the environment is text; programs convert and check it. Docker Compose reads `.env` to fill `${...}` in its YAML; that is separate from the environment inside a container, which is set by the `environment:` key.

## Walkthrough of this repository's use

### `Settings.from_env`

```python
postgres_password=_text(env, "POSTGRES_PASSWORD") if need_database else env.get("POSTGRES_PASSWORD", ""),
collector_port=collector_port,
collector_url=_text(env, "COLLECTOR_URL", f"http://127.0.0.1:{collector_port}"),
collector_token=env.get("COLLECTOR_TOKEN", "").strip(),
workdir=Path(_text(env, "GOLDENPATH_WORKDIR", ".local")),
runbook_base=_text(env, "RUNBOOK_BASE", "https://wiki.example.com/runbooks"),
```
- `_text(env, "NAME", default)` reads, strips spaces, and raises `ConfigurationError` if the result is empty.
- `_port` accepts only digits from 1 to 65535.
- `LOG_LEVEL` must be one of DEBUG, INFO, WARNING, ERROR.
- The database password is required only for commands that touch the database (`need_database` is true for `collector`, `simulate`, `metrics`, `trace`, `deployments` without `--csv`). So `goldenpath new-service` and `goldenpath audit` run with no database settings.
- The collector token has no default. The collector refuses to start without it (`configuration error: COLLECTOR_TOKEN must be set`, exit 2).
- `dsn` builds `postgresql://user:password@host:port/db` with each part passed through `urllib.parse.quote`, so a password containing `@` or `/` cannot break the URL. It holds the password, so it is never logged.

`Settings.from_env(environ)` accepts a dictionary, so tests never touch the real environment.

### Variables in the Makefile

`COSIGN_PASSWORD` unlocks the local signing key. `REGISTRY` is the registry the pipeline pushes to. They are throwaway demo values from `.env.example`; real signing in CI uses no password at all ([cosign.md](cosign.md)).

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
