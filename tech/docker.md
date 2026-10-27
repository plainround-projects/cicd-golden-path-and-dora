# Docker and the Dockerfile

## What it is

Normally a program needs the right operating-system files, libraries and settings to be present on the computer that runs it, and "it works on my machine" fails when they are not. **Docker** solves that by packaging a program together with everything it needs into one unit that runs the same way anywhere Docker is installed.

The words you need:

- A **container** is a running program that Docker has walled off: it sees its own private file system, its own list of processes and its own network, though it shares the computer's kernel (the core of the operating system). It is much lighter than a virtual machine.
- An **image** is the read-only template a container starts from: a stack of file-system **layers** plus settings. You can start many containers from one image.
- A **Dockerfile** is a text file of instructions that builds an image. `docker build` reads it.
- A **layer** is the file-system change made by one instruction. Docker keeps each layer and re-uses it when nothing before it changed, which makes rebuilds quick.
- A **registry** is a server that stores images by name (Docker Hub is a public one). `docker pull` downloads an image; `docker push` uploads one.
- A **tag** such as `3.12.8-slim-bookworm` is a movable label on an image. A **digest** (`sha256:...`) is a fingerprint of the image's exact contents and can never point at something else.
- A **port** is a numbered door (1 to 65535) on a computer that one program listens on. A container's ports are closed to the outside unless you **publish** them.
- A **health check** is a command Docker runs inside the container at intervals to decide whether the program is working.

On a Mac or Windows, Docker Desktop runs a small hidden Linux virtual machine, and the containers live inside it.

## Why this repository uses it

The golden path's artifact is a **container image**. `make image` builds it once, pushes it, and records its *digest*. That digest, not a tag, is what gets signed, verified and deployed. The same Docker engine also runs the platform's PostgreSQL and a local image registry ([docker-compose.md](docker-compose.md)), and each generated service's "production".

## Where it appears

| Path | Use |
|---|---|
| `template/Dockerfile` | The image of every generated service. |
| `template/Makefile` | `docker build -q`, `docker push` in `make image`. |
| `src/goldenpath/infrastructure/local_pipeline.py` | `build_unsigned_image`: a hand-made, unsigned image for the refusal demo. |
| `docker-compose.yml`, `template/deploy/compose.yaml` | Run containers. |

## How it works underneath

- `docker build -f Dockerfile .` sends the **build context** (the folder `.`) to the Docker engine. `COPY` can only read files from the context. The file `.dockerignore` removes files from the context before it is sent.
- The engine starts from the **base image** named in `FROM`, then runs the instructions in order, creating a layer for each that changes files. If an instruction and all before it are unchanged since the last build, the stored layer is reused. So the instructions that change least often come first.
- `RUN` executes a command **while building** and keeps the result in the image. `CMD` names the command to run **when a container starts**.
- `ENV` sets environment variables ([dotenv.md](dotenv.md)) that exist both while building later steps and when the container runs.
- `USER` sets which user the following instructions and the final program run as. A process running as a normal user cannot change the system files, which limits the damage if the program is compromised.
- The image name may include a digest after `@`. Docker then uses exactly that image, whatever the tag points at today.

## Walkthrough of this repository's use

### `template/Dockerfile`

```dockerfile
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0
ARG APP_VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
```

- **Line 1**: `FROM python:3.12.8-slim-bookworm@sha256:2199...`. `FROM` names the starting image: the official Python image, version 3.12.8, on Debian "bookworm", in the `slim` variant (smaller, with fewer extra programs). The part after `@` is that image's **digest**, so a rebuild next year starts from the same bytes even if the tag has since moved. (This is the *base* image's digest; the digest of the image *this* Dockerfile builds is a different thing, produced by the push.)
- **Line 2**: `ARG APP_VERSION=dev` declares a variable that exists only while building; `--build-arg APP_VERSION=<commit>` in `make image` gives it a value, and `dev` is the default.
- **Line 3**: `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}` sets three variables that exist when the container runs: Python writes no `.pyc` cache files (pointless in a throw-away container), prints output at once instead of holding it back (logs appear live), and the service can report its own version (`${APP_VERSION}` copies the build argument in).

```dockerfile
WORKDIR /srv
COPY app ./app
RUN useradd --system --uid 10001 --no-create-home app
USER app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]
CMD ["python", "-m", "app.main"]
```

- **Line 4**: `WORKDIR /srv` sets (and creates) the working folder. **Line 5**: `COPY app ./app` copies only the `app` folder from the build context into the image, so tests, the Makefile and `.git` never enter it.
- **Line 6**: `RUN useradd --system --uid 10001 --no-create-home app` creates an operating-system user named `app` with a fixed number, as a system account with no home folder. **Line 7**: `USER app` makes everything after, including the program that runs, use that account. A process that is not root cannot change system files, which limits the harm if it is compromised.
- **Line 8**: `EXPOSE 8080` documents that the service listens on port 8080. It publishes nothing by itself.
- **Line 9**: `HEALTHCHECK --interval=10s --timeout=20s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]`. Every 10 seconds Docker runs this command in the container; it must finish in 20 seconds; three failures in a row mark the container unhealthy. The command is Python itself: the slim image has no `curl`. `urlopen` raises an error for a failed connection or an error status, which makes the exit status non-zero. The square-bracket list form is the **exec form**: Docker runs the program directly with no shell in between, avoiding quoting surprises.
- **Line 10**: `CMD ["python", "-m", "app.main"]` is what a container runs when started: Python's `-m` runs the module `app.main`.

### Build once, then refer to the image by digest

In `template/Makefile`:

```make
# Build once, push, and keep the digest: the digest, not a tag, is what is signed, verified and deployed.
image:
	@mkdir -p .build
	docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
	docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
	@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }
	@echo "image: $(IMAGE)@$$(cat $(DIGEST_FILE))"
```

- `@mkdir -p .build` creates the folder for build records. `docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .` builds from the current folder (`.` is the *build context*), `-q` prints only the image id, `-t` tags the result `registry/name:short-commit`.
- `docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)`: `docker push` uploads the layers and the registry answers with a line containing `digest: sha256:...`; `sed` extracts that digest and `tail -1` keeps the last such line; `>` saves it to `.build/digest`. `@test -s $(DIGEST_FILE) || {...; exit 1; }` fails if nothing was saved. `@echo "image: $(IMAGE)@$$(cat $(DIGEST_FILE))"` prints the full reference.
- Everything after this (`sign`, `attest`, `verify`, `deploy`) uses `$(IMAGE)@$$(cat $(DIGEST_FILE))`, the name by digest.

### The bypass used by the refusal demo

<!-- fmt:off -->
```python
def build_unsigned_image(directory: Path, registry: str, name: str, tag: str, env: Mapping[str, str]) -> str:
    """Build and push an image by hand, the way someone bypassing the pipeline would. Returns `registry/name@digest`."""
    reference = f"{registry}/{name}:{tag}"
    built = _run(["docker", "build", "-q", "-t", reference, "."], directory, env)
    if built.returncode != 0:
        raise StepFailedError("docker build", built.stdout + built.stderr)
    pushed = _run(["docker", "push", reference], directory, env)
    if pushed.returncode != 0:
        raise StepFailedError("docker push", pushed.stdout + pushed.stderr)
    digest = next(part for line in pushed.stdout.splitlines() for part in line.split() if part.startswith("sha256:"))
    return f"{registry}/{name}@{digest}"
```
<!-- fmt:on -->

`build_unsigned_image` does what someone bypassing the pipeline would: `docker build -q -t REGISTRY/NAME:unsigned .` then `docker push`, and finds the digest in the push output (`next(part for line in pushed.stdout.splitlines() for part in line.split() if part.startswith("sha256:"))`: the first word that starts with `sha256:`). The result `REGISTRY/NAME@sha256:...` has no signature, so `deploy.sh` refuses it.

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
