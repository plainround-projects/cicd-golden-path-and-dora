# Container registry (`registry:2`)

## What it is

A **container registry** is a server that stores container images and hands them out by name. You `docker push` an image to it and `docker pull` it back. It speaks the **OCI distribution** HTTP API under the path `/v2/`. Docker Hub and GitHub's `ghcr.io` are public registries. Docker's reference implementation, called `registry` (a Go program), is small enough to run on a laptop.

## Why this repository uses it

The pipeline must push the image somewhere that signing and deploying can reach by digest. In CI that place is `ghcr.io`. On the learner's machine it is a registry container in `docker-compose.yml`, so the whole path (build, push, sign, verify, deploy) runs offline.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` | The `registry` service, published as `127.0.0.1:55061`. |
| `template/Makefile` | `REGISTRY ?= localhost:55061`; `docker push`. |
| `template/.github/workflows/ci.yml` | `REGISTRY: ghcr.io/${{ github.repository_owner }}` and `docker/login-action`. |
| `src/goldenpath/infrastructure/local_pipeline.py` | Pushes the unsigned image to the same registry. |

## How it works underneath

- An image reference has the form `host:port/name:tag` or `host:port/name@sha256:digest`.
- `docker push` uploads each layer as a **blob** (named by its digest), then uploads the **manifest**: a JSON file listing the layers. The registry returns the manifest's digest. That is the image's digest.
- `GET /v2/` answers 200 when the registry is up. `GET /v2/_catalog` lists repository names. `GET /v2/<name>/tags/list` lists tags.
- cosign stores signatures and attestations in the same repository as extra tags derived from the image digest (for example `sha256-<digest>.sig` and `.att`). The `registry` image has no "referrers" API, so cosign falls back to this tag scheme; the exact tag names depend on the cosign version.
- Docker treats `localhost` and `127.0.0.0/8` registries as insecure-allowed, so plain HTTP works for them without extra configuration.

## Walkthrough of this repository's use

```yaml
  registry:
    image: registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373
    ports:
      - "127.0.0.1:${REGISTRY_PORT:-55061}:5000"
    healthcheck:
      test: ["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"]
```
The image is pinned by digest. The registry listens on 5000 inside; the host reaches it at `localhost:55061`. The health check uses `wget` (present in the image) to fetch `/v2/`: `-q` quiet, `-O -` write the body to standard output. There is no volume, so images vanish at `make down`.

```make
REGISTRY ?= localhost:55061
IMAGE := $(REGISTRY)/$(NAME)
```
The image is `localhost:55061/orders`, tagged with the short commit. The digest saved in `.build/digest` completes the reference `localhost:55061/orders@sha256:...`.

In CI the same Makefile gets `REGISTRY=ghcr.io/<owner>` from the workflow's `env:`, and `docker/login-action` signs in with the automatic token ([github-actions.md](github-actions.md)).

## Try it yourself

```bash
make up
curl -s http://localhost:55061/v2/
```
Expect `{}`.

```bash
make demo-services
curl -s http://localhost:55061/v2/_catalog
curl -s http://localhost:55061/v2/orders/tags/list
```
The catalog lists `orders`, `billing`, `search`. The tag list holds the commit tag plus the extra tags cosign added for the signature and the attestation. These commands need Docker and were not re-run when this note was written.

```bash
curl -sI http://localhost:55061/v2/orders/manifests/$(cat .local/services/orders/.build/digest) -H "Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json" | head -3
```
Status 200 and a `Docker-Content-Digest` header equal to the saved digest.

## Mistakes people make

- Referring to an image by a tag when security matters.
- Exposing a registry with no authentication to a network.
- Forgetting that a registry with no volume forgets everything when its container is removed.
- Confusing the base image's digest (in `FROM`) with the built image's digest.

## Check yourself

1. What does `/v2/` answer on a healthy registry? *`{}` with status 200.*
2. What is the digest of an image? *The hash of its manifest, returned by the registry on push.*
3. Where does cosign store a signature? *In the same repository, as a tag derived from the digest.*
4. Why does plain HTTP work for `localhost:55061`? *Docker allows insecure access to local registries.*
5. Why no volume for the registry? *The demo needs no memory beyond one run.*

## Further reading

- Distribution (registry) documentation: https://distribution.github.io/distribution/
- OCI distribution specification: https://github.com/opencontainers/distribution-spec/blob/main/spec.md
- GitHub container registry: https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry
