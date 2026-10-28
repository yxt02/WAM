#!/usr/bin/env bash
set -euo pipefail
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"

mode=${1:-smoke}
case "$mode" in
  smoke)
    export EVAL_SUITES=libero_spatial MAX_TASKS=1 ALLOW_INCOMPLETE=1 RECORD_VIDEO=1
    ;;
  ten)
    export EVAL_SUITES=libero_spatial MAX_TASKS=10 ALLOW_INCOMPLETE=1 RECORD_VIDEO=1
    ;;
  full)
    export EVAL_SUITES=libero_spatial,libero_object,libero_goal,libero_10
    export ALLOW_INCOMPLETE=0 RECORD_VIDEO=0
    unset MAX_TASKS
    ;;
  *)
    echo "Usage: bash run_policy_plus.sh [smoke|ten|full]" >&2
    exit 64
    ;;
esac

for executable in "$POLICY_PYTHON" "$LIBERO_PLUS_PYTHON"; do
  test -x "$executable" || { echo "Missing Python: $executable" >&2; exit 1; }
done
for artifact in "$CHECKPOINT" "$DATASET_STATS" "$VJEPA2_ENCODER_CHECKPOINT" \
  "$LIBERO_CONFIG_PATH/config.yaml" "$LIBERO_PLUS_MANIFEST" "$POLICY_SERVER_SCRIPT"; do
  test -s "$artifact" || { echo "Missing or empty file: $artifact" >&2; exit 1; }
done
"$POLICY_PYTHON" -m py_compile "$POLICY_SERVER_SCRIPT"
"$POLICY_PYTHON" scripts/validate_eval_results.py cache-plus "$TEXT_EMBEDDING_CACHE" \
  --manifest "$LIBERO_PLUS_MANIFEST" --context-length 128

mkdir -p /workspace/vjepa/outputs
export EVAL_DIR
EVAL_DIR=$(mktemp -d "/workspace/vjepa/outputs/plus_${mode}_$(date -u +%Y%m%dT%H%M%SZ)_XXXXXX")
printf 'EVAL_DIR=%s\n' "$EVAL_DIR"
printf '%s\n' "$EVAL_DIR" > "/workspace/vjepa/cache/latest_plus_${mode}.path"

exec bash examples/libero_plus/evaluate_policy.sh "$RUN_DIR" "$CHECKPOINT"
