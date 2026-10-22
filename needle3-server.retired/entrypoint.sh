#!/usr/bin/env bash
set -euo pipefail

# Needle3 OpenAI-compatible API server entrypoint
# Runs as root to fix volume permissions, then drops to the needle user.

ENGINE_CACHE="${NEEDLE_CACHE_DIR:-/cache/needle}"
HF_CACHE="${HF_HOME:-/cache/huggingface}"

mkdir -p "$ENGINE_CACHE" "$HF_CACHE"
chown -R needle:needle /cache

# Hand off the OpenAI-compatible server to the non-root needle user.
# Uses custom_server.py which patches needle-openai for Needle 3 compatibility.
exec runuser -u needle -- /usr/local/bin/python /app/custom_server.py "$@"
