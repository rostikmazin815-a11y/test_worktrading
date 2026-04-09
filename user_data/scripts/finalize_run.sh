#!/usr/bin/env bash
# Stop the lab, export runtime data, and build the final analytics report.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_DIR"

echo "=== Finalizing paper-trading run ==="
bash user_data/scripts/stop_all.sh docker
echo ""
bash user_data/scripts/export_docker_results.sh
echo ""
python3 user_data/scripts/compare_results.py
echo ""
echo "Finished."
echo "Report: $PROJECT_DIR/user_data/backtest_results/paper_trading_report.md"
echo "Analysis DB: $PROJECT_DIR/user_data/backtest_results/paper_trading_analysis.sqlite"
