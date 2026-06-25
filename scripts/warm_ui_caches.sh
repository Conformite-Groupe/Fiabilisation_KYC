#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
USERS="${USERS:-20}"
RULES="${RULES:-20}"
EXTRA_ARGS="${EXTRA_ARGS:-}"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/warm_ui_caches_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"
cd "$PROJECT_ROOT"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Demarrage warm_ui_caches --users $USERS --rules $RULES $EXTRA_ARGS" | tee -a "$LOG_FILE"
# shellcheck disable=SC2086
$PYTHON_BIN manage.py warm_ui_caches --users "$USERS" --rules "$RULES" $EXTRA_ARGS 2>&1 | tee -a "$LOG_FILE"
status=${PIPESTATUS[0]}
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Fin warm_ui_caches exit=$status" | tee -a "$LOG_FILE"
exit "$status"
