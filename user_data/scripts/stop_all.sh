#!/usr/bin/env bash
# Stop all running strategy instances.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$SCRIPT_DIR/.pids"
MODE="${1:-docker}"

stop_local() {
    if [[ ! -f "$PID_FILE" ]]; then
        echo "No PID file found at $PID_FILE"
        echo "If you started the lab via Docker, run: bash user_data/scripts/stop_all.sh docker"
        exit 1
    fi

    echo "=== Stopping local strategy instances ==="
    while IFS=' ' read -r PID STRATEGY; do
        if kill -0 "$PID" 2>/dev/null; then
            echo "Stopping $STRATEGY (PID=$PID) ..."
            kill "$PID"
        else
            echo "  $STRATEGY (PID=$PID) already stopped."
        fi
    done < "$PID_FILE"

    sleep 2

    while IFS=' ' read -r PID STRATEGY; do
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force stopping $STRATEGY (PID=$PID) ..."
            kill -9 "$PID" 2>/dev/null || true
        fi
    done < "$PID_FILE"

    rm -f "$PID_FILE"
}

stop_docker() {
    cd "$PROJECT_DIR"
    echo "=== Stopping Docker strategy lab ==="
    docker compose -f docker-compose.strategies.yml down
}

case "$MODE" in
    local)
        stop_local
        ;;
    docker)
        stop_docker
        ;;
    auto)
        if docker compose -f docker-compose.strategies.yml ps --status running >/dev/null 2>&1; then
            stop_docker
        elif [[ -f "$PID_FILE" ]]; then
            stop_local
        else
            stop_docker
        fi
        ;;
    *)
        echo "Usage: bash user_data/scripts/stop_all.sh [auto|local|docker]"
        exit 1
        ;;
esac

echo ""
echo "Run analysis: python3 user_data/scripts/compare_results.py"
