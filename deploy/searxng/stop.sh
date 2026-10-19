#!/usr/bin/env bash
# Stop the local SearXNG container (configuration in ~/.config/scholarship-agent/searxng is kept).
docker rm -f scholarship-searxng >/dev/null 2>&1 && echo "stopped" || echo "not running"
