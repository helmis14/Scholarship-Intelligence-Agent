#!/usr/bin/env bash
# Start (or restart) the local SearXNG used by the Scholarship Intelligence Agent.
# Usage: deploy/searxng/start.sh [port]      default port 8080, bound to 127.0.0.1 only
set -euo pipefail
PORT="${1:-${SEARXNG_PORT:-8080}}"
NAME="scholarship-searxng"
IMAGE="searxng/searxng:latest"
CONF="${SEARXNG_CONFIG_DIR:-$HOME/.config/scholarship-agent/searxng}"
HERE="$(cd "$(dirname "$0")" && pwd)"

command -v docker >/dev/null || { echo "docker not found - install Docker Desktop" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon not running - start Docker Desktop" >&2; exit 1; }

mkdir -p "$CONF"
if [ ! -f "$CONF/settings.yml" ]; then
  key="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  sed "s/__GENERATED_BY_START_SH__/$key/" "$HERE/settings.yml" > "$CONF/settings.yml"
  chmod 600 "$CONF/settings.yml"
  echo "wrote $CONF/settings.yml"
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null
fi
docker run -d --name "$NAME" --restart unless-stopped \
  -p "127.0.0.1:${PORT}:8080" \
  -v "$CONF:/etc/searxng" \
  -e "SEARXNG_BASE_URL=http://127.0.0.1:${PORT}/" \
  --label com.centurylinklabs.watchtower.enable=false \
  "$IMAGE" >/dev/null

for i in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    echo "SearXNG up: http://127.0.0.1:${PORT}  (export SEARXNG_URL=http://127.0.0.1:${PORT})"
    exit 0
  fi
  sleep 1
done
echo "SearXNG did not become healthy; see: docker logs $NAME" >&2
exit 1
