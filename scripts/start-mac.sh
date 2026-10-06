#!/usr/bin/env bash
set -euo pipefail

APP_NAME="pm-app"
IMAGE_NAME="pm-app"
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "$SCRIPT_DIR/.." && pwd)

docker build -t "$IMAGE_NAME" "$ROOT_DIR"

docker rm -f "$APP_NAME" >/dev/null 2>&1 || true

docker run --name "$APP_NAME" --env-file "$ROOT_DIR/.env" -v pm-data:/app/backend/data -p 8000:8000 "$IMAGE_NAME"
