#!/bin/sh
# Production entrypoint: Caddy token proxy (:8080, Fly internal_port) in front
# of SearXNG/Granian on loopback (:8081). Both processes must stay alive; if
# either exits, the container exits so Fly's restart policy kicks in.
set -eu

# Fail fast (and therefore fail closed) when no edge token is configured: an
# empty SEARXNG_AUTH_TOKEN would make the Caddyfile matcher trivially matchable.
if [ -z "${SEARXNG_AUTH_TOKEN:-}" ]; then
    echo "FATAL: SEARXNG_AUTH_TOKEN is not set; refusing to start unprotected." >&2
    exit 1
fi

# SearXNG on loopback only — Caddy is the sole public surface.
export GRANIAN_HOST=127.0.0.1
export GRANIAN_PORT=8081

/usr/local/searxng/entrypoint.sh &
SEARXNG_PID=$!

caddy run --config /etc/caddy/Caddyfile &
CADDY_PID=$!

term() {
    kill "$SEARXNG_PID" "$CADDY_PID" 2>/dev/null || true
}
trap term TERM INT

while kill -0 "$SEARXNG_PID" 2>/dev/null && kill -0 "$CADDY_PID" 2>/dev/null; do
    sleep 5
done

exit 1
