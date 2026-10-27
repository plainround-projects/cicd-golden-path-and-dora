# Docker Compose

## What it is

Docker Compose runs one or more containers from a YAML file ([yaml.md](yaml.md)). You describe **services** (one container each), their ports, environment, health checks and security settings; `docker compose up` creates and starts them, `down` removes them. This repository uses the built-in `docker compose` command (version 2; v2.23.0 here).

## Why this repository uses it

Compose appears twice, for two different jobs.

1. `docker-compose.yml` (root) runs the **platform's** infrastructure: PostgreSQL for the event store and a registry for the images.
2. `template/deploy/compose.yaml` is each **service's "production"**: the verified digest, run with a locked-down configuration. It stands in for a real cluster; the file says to replace it with the delivery path from the canary project when a service moves to one.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | Services `db` and `registry`. |
| `template/deploy/compose.yaml` | Service `app`, started by `template/scripts/deploy.sh`. |
| `Makefile` | `COMPOSE := docker compose`; `up`, `db`, `down`. |

## How it works underneath

Compose reads the YAML, fills `${VAR}` from the environment and `.env`, and talks to the Docker engine to create containers and (unless told otherwise) a project network. Everything is named with a **project name** (`-p`). Services on one network reach each other by service name. A published port opens a door from the host into a container. A health check is a command Docker runs inside; `up --wait` waits for "healthy".

## Walkthrough of this repository's use

### The platform: `docker-compose.yml`

```yaml
  db:
    image: postgres:16.4-alpine
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-55441}:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 20s
      retries: 30
      start_period: 10s
    tmpfs:
      - /var/lib/postgresql/data
```
`${NAME:?message}` refuses to start without a password. `${NAME:-default}` provides defaults. The port is bound to `127.0.0.1` only (this machine) on an unusual number (55441). `$$` writes a literal `$`, so the container's shell expands the variable. The health check uses TCP (`-h 127.0.0.1`) because the image first starts a temporary server that listens only on a socket, and a socket check would say "ready" too early. `timeout: 20s` allows for a loaded laptop. `tmpfs` keeps the data in memory: fast and gone at `down` ([postgresql.md](postgresql.md)).

```yaml
  registry:
    image: registry@sha256:a3d8aaa6...
    ports:
      - "127.0.0.1:${REGISTRY_PORT:-55061}:5000"
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"]
```
The registry image is pinned by digest. Port 5000 inside is published as 55061 on the host. The health check fetches the registry's `/v2/` endpoint ([container-registry.md](container-registry.md)). `localhost:55061` counts as a "local" registry, so Docker allows plain HTTP to it.

### Each service's production: `template/deploy/compose.yaml`

```yaml
services:
  app:
    image: "${IMAGE_REF:?deploy only by digest, IMAGE_REF=registry/name@sha256:...}"
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
- `image: ${IMAGE_REF:?...}`: there is **no default**. The file refuses to start unless `deploy.sh` supplies a `registry/name@sha256:...` reference. You cannot deploy "latest" by accident.
- `network_mode: bridge` uses Docker's default network, so Compose creates no per-project network (a busy Docker that has run out of address pools can still start the service).
- `"127.0.0.1::8080"`: bind to the loopback address, let Docker pick the host port, map it to container port 8080.
- `read_only: true`: the container's file system cannot be written.
- `cap_drop: ["ALL"]`: remove every Linux capability (special privileges such as changing file owners or binding low ports).
- `no-new-privileges:true`: the process cannot gain privileges, even through a setuid program.
- The health check is the same Python one-liner as the Dockerfile's.

### How the scripts call it

```sh
IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait
```
`-p orders-production` names the project, so `make down` can remove each service's containers by name ([bash-and-sh.md](bash-and-sh.md)).

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
