# Container registry (`registry:2`)

## What it is

A container **image** ([docker.md](docker.md)) is a large bundle of files. To move it from the machine that built it to the machines that run it, you store it on a server and download it when needed. That server is a **container registry**. Docker Hub and GitHub's `ghcr.io` are public ones. Docker also publishes the program it uses itself, a small registry that is simple enough to run on a laptop, under the name `registry`.

You put an image into a registry with `docker push` and take it out with `docker pull`. Images are named like `host:port/name:tag` (a movable label) or `host:port/name@sha256:digest` (a fingerprint of the exact content that never changes). Registries speak a standard web protocol (the *OCI distribution* API) under the address path `/v2/`.

## Why this repository uses it

The pipeline must push the image somewhere that signing, verifying and deploying can all reach **by digest**. In CI that place is `ghcr.io`. On a learner's machine it is a registry container started by `docker-compose.yml`, so the whole path (build, push, sign, verify, deploy) runs offline.

## Where it appears

| Path | Use |
|---|---|
| `docker-compose.yml` lines 21 to 30 | The `registry` service, published on `127.0.0.1:55061`. |
| `template/Makefile` | `REGISTRY ?= localhost:55061`, `docker push`. |
| `template/.github/workflows/ci.yml` | `REGISTRY: ghcr.io/${{ github.repository_owner }}` and the `docker/login-action` step. |
| `src/goldenpath/infrastructure/local_pipeline.py` | Pushes the deliberately unsigned image to the same registry. |
| `Makefile` | `REGISTRY` is exported from `.env`. |

## How it works underneath

- `docker push IMAGE:TAG` uploads each **layer** of the image as a *blob* named by the hash of its content, then uploads the *manifest*: a small JSON file listing the layers and the image's settings. The registry computes the manifest's SHA-256 and replies with a line containing `digest: sha256:...`. **That digest is the image's identity.** Pushing the same content again gives the same digest.
- `GET /v2/` answers `{}` when the registry is up. `GET /v2/_catalog` lists repository names. `GET /v2/NAME/tags/list` lists tags.
- cosign stores signatures and attestations *in the same registry*, next to the image, as extra entries derived from the image's digest ([cosign.md](cosign.md)). The plain `registry` image has no "referrers" feature, so cosign uses extra tags; the tag names depend on the cosign version.
- Docker allows plain HTTP (no TLS certificate) to `localhost`, so the local registry needs no certificate set-up.

## Walkthrough of this repository's use

### The registry service

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

- **Line 21**: `registry:` is the service's name. **Line 22**: `image: registry@sha256:a3d8aaa6...` runs Docker's registry image, pinned by its digest so the platform's infrastructure is repeatable.
- **Lines 23 and 24**: `ports: - "127.0.0.1:${REGISTRY_PORT:-55061}:5000"` publishes the registry's port 5000 as port 55061 on this computer only (`127.0.0.1` is the loopback address, "this machine"). `${REGISTRY_PORT:-55061}` uses the variable or, if unset, 55061 ([dotenv.md](dotenv.md)).
- **Lines 25 to 30**: the health check `["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"]` fetches the registry's `/v2/` address (`wget` is a download program present in that image; `-q` quiet; `-O -` write the reply to standard output). The timing keys (`interval: 5s`, `timeout: 20s`, `retries: 30`, `start_period: 10s`) are explained in [docker-compose.md](docker-compose.md). There is no volume, so pushed images disappear with `make down`.

### The image name in the Makefile

```make
# make ci | release      Every job of .github/workflows/ci.yml is one of these targets, so a laptop runs the same steps.
NAME := __NAME__
REGISTRY ?= localhost:55061
VERSION ?= $(shell git rev-parse --short HEAD)
IMAGE := $(REGISTRY)/$(NAME)
DIGEST_FILE := .build/digest
```

- `REGISTRY ?= localhost:55061` is the local registry; CI overrides it with `ghcr.io/<owner>`. `IMAGE := $(REGISTRY)/$(NAME)` is the repository name, for example `localhost:55061/orders`. `VERSION` is the short commit id, used as the tag. `DIGEST_FILE := .build/digest` is where the digest is saved.

```make
# Build once, push, and keep the digest: the digest, not a tag, is what is signed, verified and deployed.
image:
	@mkdir -p .build
	docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
	docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
	@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }
	@echo "image: $(IMAGE)@$$(cat $(DIGEST_FILE))"
```

- `docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)`: the registry's reply contains `latest: digest: sha256:... size: 1234`-style lines; `sed` extracts the `sha256:...` part and the last one is saved. The saved digest completes the reference `localhost:55061/orders@sha256:...`, which is what is signed, verified and deployed ([make.md](make.md)).

### In CI

```yaml
    env:
      REGISTRY: ghcr.io/${{ github.repository_owner }}
      EVENTS_URL: ${{ vars.PLATFORM_EVENTS_URL }}
    steps:
      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2
        with:
          fetch-depth: 0
      - uses: sigstore/cosign-installer@d58896d6a1865668819e1d91763c7751a165e159 # v3.9.2
      - uses: docker/login-action@74a5d142397b4f367a81961eba4e8cd7edddf772 # v3.4.0
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```

`REGISTRY: ghcr.io/${{ github.repository_owner }}` and the login step (`registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`) let the same Makefile push to GitHub's registry using the run's automatic token, with `packages: write` granted to the release job only ([github-actions.md](github-actions.md)).

### The demonstration of an unsigned image

`build_unsigned_image` in `local_pipeline.py` pushes `REGISTRY/NAME:unsigned` and returns `REGISTRY/NAME@<digest>`. It is a perfectly valid image in the registry, with no signature next to it; `deploy.sh` refuses it ([bash-and-sh.md](bash-and-sh.md)).

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
