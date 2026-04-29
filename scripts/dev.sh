#!/usr/bin/env bash
# Local dev runner — equivalent to `make dev`, for users who prefer scripts.
# Uses console log format + DEBUG level + auto-reload on src/ changes.
set -euo pipefail

cd "$(dirname "$0")/.."

export LOG_FORMAT="${LOG_FORMAT:-console}"
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"

exec .venv/bin/uvicorn src.main:app \
  --host 0.0.0.0 \
  --port "${SERVER_PORT:-8080}" \
  --reload \
  --reload-dir src
