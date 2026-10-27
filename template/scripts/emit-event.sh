#!/bin/sh
# Record one delivery event (commit, deploy, failed, recovered) at the platform's collector.
#   usage: emit-event.sh TYPE REF [DETAIL]
# The collector's address is EVENTS_URL. The credential is EVENTS_TOKEN (a local run) or, in CI, a short-lived
# identity token requested from the CI system for the audience "goldenpath-events": no stored secret.
set -eu
type=$1
ref=$2
detail=${3:-}
: "${EVENTS_URL:?set EVENTS_URL}"
: "${SERVICE_NAME:?set SERVICE_NAME}"
token=${EVENTS_TOKEN:-}
if [ -z "$token" ] && [ -n "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ]; then
  token=$(curl -fsS -H "Authorization: Bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=goldenpath-events" | python3 -c 'import json,sys; print(json.load(sys.stdin)["value"])')
fi
payload=$(printf '{"service": "%s", "type": "%s", "ref": "%s", "detail": "%s"}' "$SERVICE_NAME" "$type" "$ref" "$detail")
curl -fsS -X POST "$EVENTS_URL/events" -H "Content-Type: application/json" -H "Authorization: Bearer $token" -d "$payload" >/dev/null
echo "event: $type $ref"
