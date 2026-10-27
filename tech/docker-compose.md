# Docker Compose

## What it is

Starting one container by hand takes a long command (`docker run --name ... -e ... -p ... image`). Starting several, wired together, takes more. **Docker Compose** lets you write that down once in a file, `docker-compose.yml`, and then run the whole set with one command. The file is written in YAML ([yaml.md](yaml.md)). This repository uses the `docker compose` command that is built into Docker (version 2; v2.23.0 here).

Compose words:

- A **service** is one container definition (an image, its settings), such as `db`.
- A **project** is the group of services started together. Compose names everything with the project name (by default, the folder name).
- A **network**: Compose puts a project's containers on a private network where they find each other by service name (the `app` container reaches the database at the host name `db`).
- A **published port** (`ports:`) opens a door from your computer into a container.
- A **volume** or **tmpfs** is where a container stores files that should outlive it (volume) or live in memory only (tmpfs).
- A **profile** hides a service unless you ask for it by name.
- A **health check** is a command Docker runs inside a container to decide whether it is ready. `up --wait` waits for "healthy".

## Why this repository uses it

Compose appears twice, for two different jobs:

1. The root `docker-compose.yml` runs the **platform's infrastructure**: PostgreSQL for the event store and a local registry for the images the pipelines build.
2. `template/deploy/compose.yaml` is each generated service's **"production"**: the verified digest, run with a locked-down configuration. It stands in for a real cluster; its comment says to replace it with the GitOps and canary path when a service moves to one.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Services `db` and `registry`. |
| `template/deploy/compose.yaml` | Service `app`, started by `template/scripts/deploy.sh`. |
| `Makefile` | `COMPOSE := docker compose`; the targets `up`, `db`, `down` use it. |
| `.env.example`, `.env` | The values Compose fills in ([dotenv.md](dotenv.md)). |

## How it works underneath

Compose reads the YAML, replaces `${NAME}` placeholders with values from the shell environment or the `.env` file in the project folder, and asks the Docker engine to create the containers, the network and the volumes. `docker compose up -d --wait db` creates and starts `db` in the background and returns once its health check passes. `docker compose exec` runs a command in a running container. `docker compose down -v` stops and removes the containers and deletes their volumes.

Compose has its own placeholder syntax: `${VAR}` (the value), `${VAR:-default}` (the value, or `default` if unset or empty) and `${VAR:?message}` (the value, or stop with `message` if unset). A `$$` writes a literal dollar sign that Compose leaves alone, so that the container's own shell can expand it.

## Walkthrough of this repository's use

### The platform: `docker-compose.yml`

```yaml
# The platform's local infrastructure: the event store and a registry for the images the pipelines build.
services:
  db:
    image: postgres:16.4-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-events}
      POSTGRES_USER: ${POSTGRES_USER:-platform}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-55441}:5432"
    # -h 127.0.0.1: the image first starts a temporary server that listens on the socket only; TCP answers when the real one is up
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 20s
      retries: 30
      start_period: 10s
    tmpfs:
      - /var/lib/postgresql/data

```

- **Line 1** (comment): the platform's local infrastructure. **Line 2**: `services:`. **Line 3**: `db:`. **Line 4**: `image: postgres:16.4-alpine`: the official PostgreSQL 16.4 server on Alpine, a very small Linux.
- **Lines 5 to 8**: `environment:` sets variables inside the container. The PostgreSQL image reads them on first start to create the database and the user. `${POSTGRES_DB:-events}` means the variable or, if unset, `events`; `${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}` has **no default**: Compose stops with that message if it is missing.
- **Lines 9 and 10**: `ports: - "127.0.0.1:${POSTGRES_PORT:-55441}:5432"`. The format is `host-address:host-port:container-port`; `127.0.0.1` means this computer only; PostgreSQL's 5432 inside is published as 55441 outside.
- **Line 11** (comment) and **lines 12 to 17**: the health check. At first start the image runs a temporary server that listens only on a Unix socket; a check over the socket would say "ready" too early, so the check forces TCP with `-h 127.0.0.1`: `pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}` (`$$` writes a literal `$`, so the *container's* shell expands the variable). `interval: 5s` (time between checks), `timeout: 20s` (how long one check may take; generous for a busy laptop), `retries: 30` (failures before "unhealthy"), `start_period: 10s` (grace time at the start).
- **Lines 18 and 19**: `tmpfs: - /var/lib/postgresql/data` keeps the data directory in memory: fast, and gone when the container is removed.

```yaml
  registry:
    image: registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373
    ports:
      - "127.0.0.1:${REGISTRY_PORT:-55061}:5000"
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"]
      interval: 5s
      timeout: 20s
      retries: 30
      start_period: 10s
```

- **Line 21**: `registry:` runs Docker's image registry ([container-registry.md](container-registry.md)). **Line 22**: `image: registry@sha256:a3d8aaa6...`: pinned by digest. **Lines 23 and 24**: `ports: - "127.0.0.1:${REGISTRY_PORT:-55061}:5000"`: the registry listens on 5000 inside; it is published as 55061 on this computer only.
- **Lines 25 to 30**: the health check `["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"]` fetches the registry's `/v2/` address with `wget` (present in that image): `-q` quiet, `-O -` write the reply to standard output. Same timing keys as above.

### Each service's "production": `template/deploy/compose.yaml`

```yaml
# The local "production": the verified digest, run by compose. Replace with the platform's delivery path
# (GitOps and a canary, see the cicd-canary-with-rollback project) when the service moves to a cluster.
services:
  app:
    image: "${IMAGE_REF:?deploy only by digest, IMAGE_REF=registry/name@sha256:...}"
    # The default bridge: no per-project network to create, so a busy Docker daemon (or one that has run out of
    # address pools) can still start the service.
    network_mode: bridge
    ports:
      - "127.0.0.1::8080"
    read_only: true
    cap_drop: ["ALL"]
    security_opt: ["no-new-privileges:true"]
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
      interval: 5s
      timeout: 20s
      retries: 12
      start_period: 5s
```

- **Lines 1 and 2** (comments): the verified digest, run by Compose; replace it with the platform's delivery path when the service moves to a cluster.
- **Line 5**: `image: "${IMAGE_REF:?deploy only by digest, IMAGE_REF=registry/name@sha256:...}"`. There is **no default**: the file refuses to start unless `deploy.sh` supplies a reference by digest. You cannot deploy "latest" by accident.
- **Lines 6 to 8**: `network_mode: bridge` uses Docker's default network, so Compose creates no network for the project (an overloaded Docker that has run out of address pools can still start the service).
- **Lines 9 and 10**: `ports: - "127.0.0.1::8080"`: publish container port 8080 on this computer only, on a host port Docker picks.
- **Line 11**: `read_only: true` makes the container's file system read-only. **Line 12**: `cap_drop: ["ALL"]` removes every Linux *capability* (special privileges such as changing file owners or binding low ports). **Line 13**: `security_opt: ["no-new-privileges:true"]` forbids the process from gaining privileges, even through a program with the setuid bit.
- **Lines 14 to 19**: the health check runs the same Python one-liner as the Dockerfile every 5 seconds with 12 retries and a 5-second start period.

### How the scripts and Make drive it

`deploy.sh` runs `IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait` (`-p` names the project so `make down` can find the containers; `--wait` waits for "healthy") ([bash-and-sh.md](bash-and-sh.md)). `make up` runs `docker compose up -d --wait`; `make down` runs `docker compose down -v` and, for each generated service, `docker compose -p NAME-production -f .../deploy/compose.yaml down -v` ([make.md](make.md)).

## Try it yourself

```bash
make -B .env >/dev/null
docker compose config --quiet && echo valid
```
Prints `valid` when the platform file parses.

```bash
IMAGE_REF=unused docker compose -f template/deploy/compose.yaml config | grep -E "read_only|cap_drop|no-new-privileges|network_mode"
```
Expect lines for `cap_drop`, `network_mode: bridge`, `read_only: true` and `no-new-privileges:true`.

```bash
docker compose -f template/deploy/compose.yaml config 2>&1 | tail -1
```
Without `IMAGE_REF` it stops with `error while interpolating services.app.image: required variable IMAGE_REF is missing a value: deploy only by digest, ...`.

```bash
make up && docker compose ps
```
`db` and `registry` both `running (healthy)`.

## Mistakes people make

- Running production by a tag. Here the file demands a digest.
- Leaving the root file system writable and all capabilities on.
- Publishing a database port on all interfaces.
- Using `localhost` as a host name between containers.
- Forgetting `$$` in a health check.

## Check yourself

1. What does `${IMAGE_REF:?...}` do? *Stops the command if the variable is not set.*
2. What does `cap_drop: ["ALL"]` do? *Removes all special Linux privileges from the container.*
3. Why `127.0.0.1::8080`? *Publishes on this machine only, with a host port chosen by Docker.*
4. What does `read_only: true` prevent? *Writing to the container's file system.*
5. Why pin the registry image by digest? *The platform's infrastructure is then repeatable.*

## Further reading

- Compose file reference: https://docs.docker.com/reference/compose-file/
- Security options and capabilities: https://docs.docker.com/engine/containers/run/#runtime-privilege-and-linux-capabilities
- `docker compose up --wait`: https://docs.docker.com/reference/cli/docker/compose/up/
