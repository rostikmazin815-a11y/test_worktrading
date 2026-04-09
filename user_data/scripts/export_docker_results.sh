#!/usr/bin/env bash
# Export DBs and logs from Docker volumes to local files without bind mounts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.strategies.yml"
TARGET_USER_DATA="$PROJECT_DIR/user_data"

mkdir -p "$TARGET_USER_DATA"
rm -rf "$TARGET_USER_DATA/dbs" "$TARGET_USER_DATA/logs" "$TARGET_USER_DATA/backtest_results"

echo "Exporting runtime data from Docker Compose volumes ..."
docker compose -f "$COMPOSE_FILE" cp dashboard:/app/user_data/dbs "$TARGET_USER_DATA/dbs"
docker compose -f "$COMPOSE_FILE" cp dashboard:/app/user_data/logs "$TARGET_USER_DATA/logs"
docker compose -f "$COMPOSE_FILE" cp dashboard:/app/user_data/backtest_results "$TARGET_USER_DATA/backtest_results" 2>/dev/null || true

echo "Exported to: $TARGET_USER_DATA"
