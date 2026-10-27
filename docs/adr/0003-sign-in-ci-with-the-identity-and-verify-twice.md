# 3. Sign with the CI identity, verify in the pipeline and again in the deploy script

Status: accepted, 2026-10-27

## Context

Step 3 asks that an unsigned image is refused at deployment and that no long-lived credential exists in a generated repository. Sigstore's keyless signing needs a public OIDC identity (a CI system); a laptop has none.

## Decision

The template's workflow signs keylessly with the job's short-lived identity token (`cosign sign`, the release job alone holds `id-token: write`) and verifies with the workflow identity and issuer. The same Makefile runs on a laptop with `COSIGN_KEY` (a local key pair created by `make up`, in `.local/keys`, never in a generated repository) and `COSIGN_PUBLIC_KEY`, signing without the public transparency log. Provenance (builder, repository, commit, time) is attached as an attestation to the signed digest and verified with it. Verification runs as a pipeline step and again inside `scripts/deploy.sh`, so calling the deploy script directly with an image nobody signed is refused, and the refusal is recorded as a `failed` event with detail `signature`.

## Alternatives considered

- **Verify only in the pipeline:** a manual deployment of an unsigned image would pass.
- **An admission policy in the cluster** (Kyverno or the Sigstore policy controller): the right place for a cluster target and the lesson's hint. This build deploys with compose, so there is no admission controller to configure; the deploy script is the gate, and the README says what the cluster version adds.

## Consequences

- The keyless path (OIDC, Fulcio, Rekor) is written and audited but cannot run off GitHub; the key path is run end to end here.
- The audit searches every generated file for what a stored credential looks like, and refuses a repository that has one.
