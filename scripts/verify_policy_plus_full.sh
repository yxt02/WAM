#!/usr/bin/env bash
set -euo pipefail
source /workspace/vjepa/scripts/policy_plus.env
cd "$POLICY_REPO"
EVAL_DIR=${1:?Usage: bash verify_policy_plus_full.sh EVAL_DIR}
test -d "$EVAL_DIR" || { echo "Missing result directory: $EVAL_DIR" >&2; exit 1; }
result_tmp=$(mktemp)
trap 'rm -f "$result_tmp"' EXIT
"$POLICY_PYTHON" scripts/validate_eval_results.py libero-plus "$EVAL_DIR" \
  --manifest "$EVAL_DIR/task_manifest.json" > "$result_tmp"
"$POLICY_PYTHON" - "$EVAL_DIR" "$result_tmp" <<'PY'
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])
result = json.loads(Path(sys.argv[2]).read_text())
expected = {
    "libero_spatial": 2402,
    "libero_object": 2518,
    "libero_goal": 2591,
    "libero_10": 2519,
}
if result.get("complete") is not True or result.get("selected_complete") is not True:
    raise SystemExit("Incomplete benchmark")
if result.get("episodes") != 10030 or result.get("suites") != expected:
    raise SystemExit("Wrong suite/episode coverage")
for suite in expected:
    status = (directory / f"{suite}.status").read_text().strip()
    if status != "0":
        raise SystemExit(f"Worker failed: {suite}, status={status}")
print(json.dumps(result, indent=2))
print("Full LIBERO-Plus coverage verified: 10030/10030")
PY
cp "$result_tmp" "$EVAL_DIR/results.revalidated.json"
