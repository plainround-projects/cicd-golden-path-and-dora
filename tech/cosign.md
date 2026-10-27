# cosign (signing and verifying container images)

## What it is

cosign is a command-line tool from the Sigstore project that signs container images and checks those signatures. A **digital signature** is a piece of data that only the holder of a private key could have made, and that anyone with the matching public key can check. If the signature checks out, you know two things: who signed it, and that the signed bytes have not changed. cosign stores the signature **in the registry**, next to the image. An **attestation** is a signed statement about an image (here: which commit and which build produced it). This repository uses cosign 3.x.

## Why this repository uses it

The golden path's second non-negotiable rule is: *we must know that what runs is what CI built.* The release pipeline signs every image, attaches a provenance attestation, and verifies both before deploying. An image that someone built and pushed by hand has no signature and is refused.

## Where it appears

| Path | Use |
|---|---|
| `template/Makefile` | `cosign sign`, `cosign attest` (targets `sign`, `attest`). |
| `template/scripts/verify.sh` | `cosign verify`, `cosign verify-attestation`. |
| `template/scripts/deploy.sh` | Calls `verify.sh` before anything runs. |
| `template/.github/workflows/ci.yml` | `sigstore/cosign-installer` installs cosign on the runner. |
| `Makefile` (root) | `cosign generate-key-pair` makes the local demo key once. |
| `src/goldenpath/domain/rules.py` | `GP-SIGN` and `GP-VERIFY`: the audit requires these steps. |

## How it works underneath

- An image is identified by its **digest**. cosign signs that digest, not a tag. The signature is pushed to the same repository under a tag derived from the digest (for example `sha256-<digest>.sig`; the exact scheme depends on the cosign version and the registry).
- **Key-based** signing: a key pair (`cosign.key` private, `cosign.pub` public). Verification needs the public key.
- **Keyless** signing (used in CI): there is no long-lived key. The CI job gets a short-lived identity token from GitHub ([oidc-identity-tokens.md](oidc-identity-tokens.md)). Sigstore's certificate authority (Fulcio) issues a certificate for a few minutes, tying a public key to that identity. cosign signs, records the event in a public **transparency log** (Rekor), and throws the key away. A verifier checks the certificate's identity (which workflow, which repository) and issuer.
- An attestation is a signed JSON document (a **predicate**) about the digest. `--type custom` means "any JSON".

## Walkthrough of this repository's use

### Making the local demo key

```make
@test -f $(KEYS)/cosign.key || (cd $(KEYS) && COSIGN_PASSWORD="$(COSIGN_PASSWORD)" cosign generate-key-pair >/dev/null && echo "created a local signing key pair in $(KEYS)")
```
Create `cosign.key` and `cosign.pub` in `.local/keys` if the key is missing. The private key is encrypted with the password in `COSIGN_PASSWORD` (a throwaway value from `.env`). `.gitignore` excludes `keys/` and `*.key`.

### Signing

```make
KEY_FLAGS = --timeout=15m $(if $(COSIGN_KEY),--key $(COSIGN_KEY) --use-signing-config=false --tlog-upload=false,)
sign:
	cosign sign --yes $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))
```
- `--yes` answers the confirmation prompts, so CI never waits for a person.
- `--timeout=15m` replaces the default three minutes, because a busy machine or network can need longer.
- With `COSIGN_KEY` set (local): `--key FILE` signs with that key. cosign 3 normally uses a "signing config" that sends the signature to public Sigstore services; `--use-signing-config=false` turns that off and `--tlog-upload=false` skips the public transparency log, so the offline demo works.
- With no key (CI): none of those flags are added, so cosign signs **keyless** using the job's identity.

### Attesting

```make
cosign attest --yes --type custom --predicate .build/provenance.json $(KEY_FLAGS) $(IMAGE)@$$(cat $(DIGEST_FILE))
```
Attaches the provenance file (builder, repository, commit, build time) as a signed attestation of the same digest.

### Verifying

```sh
cosign verify --timeout=15m --key "$COSIGN_PUBLIC_KEY" --insecure-ignore-tlog=true "$image"
cosign verify-attestation --timeout=15m --key "$COSIGN_PUBLIC_KEY" --type custom --insecure-ignore-tlog=true "$image"
```
Local: check the signature and the attestation with the public key. `--insecure-ignore-tlog=true` skips the transparency-log check, because the demo never uploaded to the log. The flag's name says it: use it only for a local demo.

```sh
identity="^https://github.com/${GITHUB_REPOSITORY}/.github/workflows/ci.yml@.*$"
issuer="https://token.actions.githubusercontent.com"
cosign verify --certificate-identity-regexp "$identity" --certificate-oidc-issuer "$issuer" "$image"
```
CI: accept the signature only if the certificate names **this repository's `ci.yml`** and was issued for a GitHub Actions token. A signature made by anyone else, or from a different workflow, fails.

### What failure looks like

`goldenpath demo-unsigned` pushes an image by hand. `verify.sh` fails with `no signatures found`, `deploy.sh` prints `deploy refused: ... does not verify`, records a `failed` event with detail `signature`, and exits 1. The refusal shows up in the metrics as `refused`.

### Keyless was written, not run

The keyless branch of the Makefile and `verify.sh`, and the CI workflow, are written to work on GitHub. They need a real GitHub repository with an identity provider, so they were **not run** during the build of this repository; only the key-based path was.

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
