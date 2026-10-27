#!/bin/sh
# Refuse anything that is not signed and attested by this repository's pipeline. Used by `make verify` and by
# scripts/deploy.sh, so the deploy path cannot be reached with an unsigned image.
#   usage: verify.sh IMAGE@sha256:...
# CI uses keyless verification (the identity is this repository's workflow); a local run uses COSIGN_PUBLIC_KEY.
set -eu
image=$1
# cosign writes its report to standard error; it is shown only when a check fails.
quiet() {
  if ! output=$("$@" 2>&1 >/dev/null); then
    printf '%s\n' "$output" >&2
    exit 1
  fi
}
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
echo "verified: $image"
