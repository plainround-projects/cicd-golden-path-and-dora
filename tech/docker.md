# Docker and the Dockerfile

## What it is

Docker runs programs inside **containers**. A container is an ordinary process that sees its own private file system, network and process list; it shares the host's kernel, so it is lighter than a virtual machine. An **image** is the read-only template a container starts from: a stack of file-system **layers** plus settings. A **Dockerfile** is a list of instructions that builds an image. A **registry** stores images by name; an image has a **tag** (a movable label such as `abc1234`) and a **digest** (`sha256:...`, the fingerprint of its exact content, which cannot move). On a Mac, Docker Desktop runs a small Linux VM that holds the containers.

## Why this repository uses it

The golden path's artifact is a container image. `make image` builds it once, pushes it, and records its **digest**. That digest is what gets signed, verified and deployed. The same Docker engine also runs the platform's PostgreSQL and registry ([docker-compose.md](docker-compose.md)).

## Where it appears

| Path | Use |
|---|---|
| `template/Dockerfile` | The image of every generated service. |
| `template/Makefile` | `docker build -q`, `docker push` in `make image`. |
| `src/goldenpath/infrastructure/local_pipeline.py` | `build_unsigned_image`: the bypass attempt (`docker build`, `docker push`). |
| `docker-compose.yml`, `template/deploy/compose.yaml` | Run containers. |

## How it works underneath

- `docker build` starts at `FROM`, runs each instruction in order and caches each layer; unchanged steps are reused. Put what rarely changes first.
- The **build context** (`.`) is the folder sent to the builder; `COPY` can read only from it.
- `docker push registry/name:tag` uploads the layers and the **manifest** (the list of layers). The registry replies with the manifest's digest. That digest is the identity of the image.
- `RUN` happens at build time; `CMD` at start time. `USER` selects who the process runs as. `HEALTHCHECK` is a command Docker runs inside the container to decide if it is healthy.

## Walkthrough of this repository's use

```dockerfile
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0
```
Python 3.12.8 on Debian bookworm, the `slim` variant. The `@sha256:` part pins the exact base image, so a rebuild next year starts from the same bytes. (The base-image digest and the image's own digest are different things.)

```dockerfile
ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
```
`ARG` is a build-time variable (`--build-arg APP_VERSION=<commit>` in `make image`). `ENV` sets runtime variables: no `.pyc` files, unbuffered output, and the version the service reports at `/`.

```dockerfile
WORKDIR /srv
COPY app ./app
```
Work in `/srv` and copy only the `app` folder. Tests, the Makefile and `.git` do not enter the image.

```dockerfile
RUN useradd --system --uid 10001 --no-create-home app
USER app
```
Create a system user with a fixed id and run as it. A process that is not root cannot change the image's files or install packages.

```dockerfile
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["python", "-m", "app.main"]
```
`EXPOSE` documents the port; it publishes nothing. The health check uses only Python's standard library, because the slim image has no `curl`. Success is exit status 0; `urlopen` raises on an error status or a refused connection. `CMD` in the list (**exec**) form runs Python directly without a shell.

### The image is built once, then referred to by digest

```make
docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
```
`-q` prints only the image id. After the push, the digest is cut out of the output and saved. Everything later (`cosign sign`, `cosign verify`, `deploy`) uses `registry/name@sha256:...`.

### The bypass in `build_unsigned_image`

It runs the same `docker build` and `docker push` by hand, with the tag `unsigned`, and returns `registry/name@<digest>`. Nothing signs it. `demo-unsigned` then tries to deploy it and shows the refusal.

## Try it yourself

```bash
docker --version
docker build --help | head -3
```

```bash
make demo-services
docker image ls | grep -E "orders|billing|search" | head
```
(Needs `make up` first.) Each service has an image tagged with its short commit.

```bash
curl -s http://localhost:55061/v2/_catalog
```
Lists the repositories in the local registry: `{"repositories":["billing","orders","search"]}`.

```bash
docker inspect --format '{{.Config.User}} {{.Config.Healthcheck.Test}}' $(docker image ls -q localhost:55061/orders | head -1)
```
Expect `app [CMD python -c import urllib.request; ...]`.

## Mistakes people make

- Deploying by a tag. A tag can point at a different image tomorrow.
- Running as root.
- Putting the whole project into the image, including secrets and tests.
- Installing `curl` only to run a health check; here Python does it.
- Leaving the base image on a moving tag; here it is pinned by digest.

## Check yourself

1. What is the difference between a tag and a digest? *A tag can move; a digest names exact content.*
2. Why is only `app/` copied? *To keep tests, tools and history out of the image.*
3. Why does the health check call Python? *The slim image has no `curl`.*
4. What does `USER app` do? *Runs the service without root rights.*
5. Where does the digest come from? *The registry's reply to `docker push`.*

## Further reading

- Dockerfile reference: https://docs.docker.com/reference/dockerfile/
- Pulling by digest: https://docs.docker.com/reference/cli/docker/image/pull/
- Base image: https://hub.docker.com/_/python (3.12.8-slim-bookworm)
