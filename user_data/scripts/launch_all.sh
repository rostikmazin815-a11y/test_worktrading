#!/usr/bin/env bash
# Launch all strategy instances for the paper-trading experiment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$SCRIPT_DIR/.pids"
MODE="${1:-docker}"

ensure_not_running() {
    if [[ -f "$PID_FILE" ]] && [[ -s "$PID_FILE" ]]; then
        echo "PID file already exists: $PID_FILE"
        echo "If the lab is still running, stop it first: bash user_data/scripts/stop_all.sh"
        exit 1
    fi
}

launch_local() {
    echo "Local mode is no longer supported in this lab."
    echo "Use Docker Compose: bash user_data/scripts/launch_all.sh"
    exit 1
}

launch_docker() {
    cd "$PROJECT_DIR"
    echo "=== Launching strategy lab with Docker Compose ==="
    mkdir -p user_data/dbs user_data/logs user_data/backtest_results
    docker compose -f docker-compose.strategies.yml up -d --build
    echo "Containers started from docker-compose.strategies.yml"
}

case "$MODE" in
    local)
        launch_local
        ;;
    docker)
        launch_docker
        ;;
    auto)
        if command -v docker >/dev/null 2>&1; then
            launch_docker
        elif command -v freqtrade >/dev/null 2>&1; then
            launch_local
        else
            echo "Neither docker nor freqtrade is available in PATH."
            exit 1
        fi
        ;;
    *)
        echo "Usage: bash user_data/scripts/launch_all.sh [auto|local|docker]"
        exit 1
        ;;
esac

echo ""
if [[ "$MODE" == "local" ]]; then
    echo "To stop all: bash user_data/scripts/stop_all.sh local"
else
    echo "To stop all: bash user_data/scripts/stop_all.sh docker"
fi
echo "To compare results: python3 user_data/scripts/compare_results.py"
