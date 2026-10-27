# make ci | release      Every job of .github/workflows/ci.yml is one of these targets, so a laptop runs the same steps.
NAME := __NAME__
REGISTRY ?= localhost:55061
VERSION ?= $(shell git rev-parse --short HEAD)
IMAGE := $(REGISTRY)/$(NAME)
DIGEST_FILE := .build/digest
# Signing: with COSIGN_KEY (a local key file) the key is used; with none, CI's keyless identity is.
# (cosign 3 needs --use-signing-config=false to sign with a key and without the public transparency log.)
COSIGN_KEY ?=
COSIGN_PUBLIC_KEY ?=
# cosign gives up after three minutes by default; a busy machine or a slow network can need longer.
KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)
DEPLOYMENT ?= $(NAME)-d$(shell date +%s)
export EVENTS_URL SERVICE_NAME := $(NAME)
export COSIGN_PUBLIC_KEY

.PHONY: lint test ci image sign attest verify deploy release

lint:
	python3 -m compileall -q app tests

test:
	python3 -m unittest discover -s tests

ci: lint test

# Build once, push, and keep the digest: the digest, not a tag, is what is signed, verified and deployed.
image:
	@mkdir -p .build
	docker build -q --build-arg APP_VERSION=$(VERSION) -t $(IMAGE):$(VERSION) .
	docker push $(IMAGE):$(VERSION) | sed -n 's/.*digest: \(sha256:[0-9a-f]*\).*/\1/p' | tail -1 > $(DIGEST_FILE)
	@test -s $(DIGEST_FILE) || { echo "no digest in the push output"; exit 1; }
	@echo "image: $(IMAGE)@$$(cat $(DIGEST_FILE))"

sign:
	cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))

# A provenance statement: which commit and which build produced the digest.
attest:
	@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
	  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
	cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))

verify:
	scripts/verify.sh $(IMAGE)@$$(cat $(DIGEST_FILE))

deploy:
	scripts/deploy.sh $(NAME) $(IMAGE)@$$(cat $(DIGEST_FILE)) $(DEPLOYMENT) "$(COMMITS)"

release: image sign attest verify deploy
