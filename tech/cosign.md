# cosign (signing and verifying container images)

## What it is

A **digital signature** is a piece of data that only the holder of a **private key** could have produced for a given file, and that anyone holding the matching **public key** can check. If the check passes you know two things: *who* signed, and that the signed bytes have *not changed* since. A private key and a public key together are a **key pair**. The private half must stay secret.

**cosign** is a command-line program, from the Sigstore project, that signs container images and checks those signatures. It stores the signature *in the registry* next to the image ([container-registry.md](container-registry.md)). It can also attach an **attestation**: a signed statement about an image, here "which commit and which build produced this digest" (**provenance**). This repository uses cosign 3.x (3.1.4 on the machine it was built on).

There are two ways to sign:

- **With a key.** You make a key pair once (`cosign generate-key-pair`) and sign with the private key. Verifiers need the public key. This is what the local demo does.
- **Keyless.** There is no long-lived key at all. The CI job asks its platform for a short-lived identity token ([oidc-identity-tokens.md](oidc-identity-tokens.md)). Sigstore's certificate authority issues a certificate that lasts a few minutes and ties a fresh public key to *that identity* (for example "the workflow `ci.yml` of repository owner/name"). cosign signs with it, records the event in a public **transparency log** (a tamper-evident, append-only public list), and discards the key. A verifier checks the certificate's identity and issuer instead of holding a key.

## Why this repository uses it

The golden path's second non-negotiable rule is: *we must know that what runs is what CI built.* The release pipeline signs every image, attaches a provenance statement, verifies both, and only then deploys. An image that someone built and pushed by hand has no signature, and the deploy script refuses it.

## Where it appears

| Path | Use |
|---|---|
| `template/Makefile` | `cosign sign` (target `sign`) and `cosign attest` (target `attest`), plus the `KEY_FLAGS` variable. |
| `template/scripts/verify.sh` | `cosign verify` and `cosign verify-attestation`. |
| `template/scripts/deploy.sh` | Calls `verify.sh` before anything runs. |
| `template/.github/workflows/ci.yml` | `sigstore/cosign-installer` installs cosign on the runner. |
| `Makefile` (root) | `cosign generate-key-pair` creates the local demo key once. |
| `src/goldenpath/domain/rules.py` | `GP-SIGN` and `GP-VERIFY`: the audit requires these steps in every workflow. |
| `src/goldenpath/infrastructure/local_pipeline.py` | The unsigned-image demonstration. |

## How it works underneath

- cosign signs the image's **digest**, not a tag. A tag can later point at different content; a digest cannot, so a signature on a digest is a statement about exact bytes.
- The signature and the attestation are small objects stored in the same repository, with names derived from the digest.
- An attestation has a **type** and a **predicate** (the statement). `--type custom` means "any JSON document", here the provenance file.
- Verification fetches the signature from the registry and checks it against the public key (key mode) or against the certificate's identity and issuer (keyless mode).
- cosign normally also talks to public Sigstore services (a signing configuration, the transparency log). Flags below turn that off for the offline demo.

## Walkthrough of this repository's use

### Making the demo key pair

```make
up: $(STAMP) .env ## start PostgreSQL and the registry, create a signing key, apply sql/, start the collector
	$(COMPOSE) up -d --wait
	$(MAKE) --no-print-directory db
	@mkdir -p $(KEYS) .local/logs
	@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created a local signing key pair in $(KEYS)")
	@$(MAKE) --no-print-directory collector
```

Inside `up`: `@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created a local signing key pair in $(KEYS)")` means: if `.local/keys/cosign.key` does not exist, then (in a sub-shell, so the `cd` does not leak) generate `cosign.key` (private) and `cosign.pub` (public) in that folder. The private key is encrypted with the password in `COSIGN_PASSWORD`, a throw-away value from `.env` ([dotenv.md](dotenv.md)). `>/dev/null` hides the output. The folder is in `.local/`, and `keys/` and `*.key` are in `.gitignore`.

### Signing and attesting: `template/Makefile`

```make
# Signing: with COSIGN_KEY (a local key file) the key is used; with none, CI's keyless identity is.
# (cosign 3 needs --use-signing-config=false to sign with a key and without the public transparency log.)
COSIGN_KEY ?=
COSIGN_PUBLIC_KEY ?=
# cosign gives up after three minutes by default; a busy machine or a slow network can need longer.
KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)
DEPLOYMENT ?= $(NAME)-d$(shell date +%s)
export EVENTS_URL SERVICE_NAME := $(NAME)
export COSIGN_PUBLIC_KEY
```

- **Lines 7 to 10**: comments and the variables `COSIGN_KEY` and `COSIGN_PUBLIC_KEY` (both empty by default). **Line 11**: the comment "cosign gives up after three minutes by default; a busy machine or a slow network can need longer".
- **Line 12**: `KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)`. `--timeout=15m` replaces the three-minute default. `$(if CONDITION,THEN,ELSE)` is `make`'s own `if`: when `COSIGN_KEY` is set (the local demo) add `--key FILE` (sign with this key), `--use-signing-config=false` (cosign 3 would otherwise contact Sigstore's public services to get a signing configuration) and `--tlog-upload=false` (do not upload to the public transparency log); when it is empty (CI) add nothing, so cosign signs keyless as the CI identity. The `=` (not `:=`) makes `make` work this out each time it is used.

```make
sign:
	cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))

# A provenance statement: which commit and which build produced the digest.
attest:
	@printf '{"builder": "%s", "repository": "%s", "commit": "%s", "built_at": "%s"}\n' \
	  "$${GITHUB_WORKFLOW:-local}" "$(NAME)" "$$(git rev-parse HEAD)" "$$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .build/provenance.json
	cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))
```

- **Lines 35 and 36**, `sign`: `cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))`. `--yes` answers cosign's confirmation questions so a pipeline never waits for a person. The image is named by digest: `$$(cat .build/digest)` reads the saved digest.
- **Lines 38 to 42**, `attest`: first a `printf` writes `.build/provenance.json`, a small JSON statement of the builder (`$${GITHUB_WORKFLOW:-local}`: the workflow's name, or `local` on a laptop), the repository, the full commit and the UTC time; then `cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) IMAGE@DIGEST` signs that statement and attaches it to the image.

### Verifying: `template/scripts/verify.sh`

```sh
if [ -n "${COSIGN_PUBLIC_KEY:-}" ]; then
  quiet cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"
  quiet cosign verify-attestation --timeout=15m --key "$COSIGN_PUBLIC_KEY" --type custom --insecure-ignore-tlog=true "$image"
else
  : "${GITHUB_REPOSITORY:?set GITHUB_REPOSITORY or COSIGN_PUBLIC_KEY}"
  identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"
  issuer="https://token.actions.githubusercontent.com"
  quiet cosign verify --timeout=15m --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
  quiet cosign verify-attestation --timeout=15m --type custom --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
fi
```

- **Key mode** (when `COSIGN_PUBLIC_KEY` is set): `cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"` and `cosign verify-attestation ... --type custom ...` check the signature and the provenance against the public key. `--insecure-ignore-tlog=true` skips the transparency-log check because the demo signed with `--tlog-upload=false`; the flag's name tells you it is for a demo only.
- **Keyless mode** (CI): `identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"` and `issuer="https://token.actions.githubusercontent.com"`, then `cosign verify --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"`. The signature is accepted only if the certificate's identity matches this repository's `ci.yml` workflow and was issued for a GitHub Actions token. A signature from another repository or workflow does not match. The same two flags are used for `verify-attestation`. Every line is explained in [bash-and-sh.md](bash-and-sh.md).

### The refusal

`goldenpath demo-unsigned NAME` pushes an image by hand and runs `scripts/deploy.sh`. `verify.sh` fails (cosign reports `no signatures found`), `deploy.sh` prints `deploy refused: ... does not verify`, records a `failed` event with the detail `signature`, and exits 1. In the metrics this appears as `refused` ([dora-metrics.md](dora-metrics.md)).

### The audit

`GP-SIGN` and `GP-VERIFY` in `rules.check_workflow` fail the audit of any generated repository whose workflow lacks a step containing `make sign` or `cosign sign`, and one containing `make verify` or `cosign verify` ([github-actions.md](github-actions.md)).

### What was run and what was not

Only the **key-based** path was run here (a local registry, a local key pair). The keyless path is written (the empty `COSIGN_KEY` branch, the CI branch of `verify.sh`, the workflow) but needs a real GitHub repository with an identity provider, so it was **not run**.

## Try it yourself

```bash
cosign version
```
Expect a 3.x version.

```bash
make up
ls .local/keys
```
Expect `cosign.key` and `cosign.pub`.

```bash
make demo-services
make demo-unsigned
```
The second prints a line with `no signatures found` or `deploy refused`, then `deploy exit status: 1 (refused)`.

```bash
cd .local/services/orders && cosign verify --key ../../keys/cosign.pub --insecure-ignore-tlog=true localhost:55061/orders@$(cat .build/digest) | head -c 300
```
Prints JSON describing the verified signature.

## Mistakes people make

- Signing a tag. A tag can move after signing; sign and verify the digest.
- Verifying "some signature exists" without checking *who* signed it. The CI mode pins the workflow identity.
- Keeping a long-lived signing key in CI secrets. Keyless avoids it.
- Using `--insecure-ignore-tlog` outside a local demo.
- Committing a private key. `.gitignore` excludes `*.key`; the audit scans for private keys.

## Check yourself

1. What does a signature prove? *Who signed it and that the signed bytes have not changed.*
2. Why sign the digest? *A digest names exact content; a tag does not.*
3. What is keyless signing? *Signing with a short-lived certificate tied to the CI job's identity, so no long-lived key exists.*
4. What does `--certificate-identity-regexp` check? *That the signer was this repository's workflow.*
5. What is an attestation? *A signed statement about an image, here its provenance.*

## Further reading

- Sigstore cosign documentation: https://docs.sigstore.dev/cosign/
- Signing containers: https://docs.sigstore.dev/cosign/signing/signing_with_containers/
- Verifying: https://docs.sigstore.dev/cosign/verifying/verify/
- Attestations: https://docs.sigstore.dev/cosign/verifying/attestation/
- Keyless signing overview: https://docs.sigstore.dev/cosign/signing/overview/
