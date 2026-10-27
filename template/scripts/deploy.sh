#!/bin/sh
# Deploy a digest, but only after it verifies. A failed verification is recorded as a failed deployment and nothing runs.
#   usage: deploy.sh NAME IMAGE@sha256:... DEPLOYMENT_ID COMMITS   (COMMITS: ids joined by +)
set -eu
name=$1
image=$2
deployment=$3
commits=$4
here=$(cd "$(dirname "$0")/.." && pwd)

if ! "$here/scripts/verify.sh" "$image"; then
  echo "deploy refused: $image does not verify" >&2
  "$here/scripts/emit-event.sh" failed "$deployment" signature || true
  exit 1
fi
IMAGE_REF="$image" docker compose -p "$name-production" -f "$here/deploy/compose.yaml" up -d --wait
"$here/scripts/emit-event.sh" deploy "$deployment:$commits"
echo "deployed: $image as $name-production"
