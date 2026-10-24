#!/usr/bin/env bash
# Assemble the container build context (./app) for the recognizer worker.
#
#   ./assemble.sh            # CARNATIC model (default) — reliability-only cutover, no behaviour change
#   ./assemble.sh dual       # DUAL model (Carnatic + Hindustani) — the Hindustani launch build
#   ./assemble.sh swara      # DUAL classes + swara chains (tools/train_swara) — the current build
#
# Default is carnatic ON PURPOSE: the first cutover should only move hosting off the sleeping HF
# Space with IDENTICAL predictions, so it is a pure, low-risk reliability win. Build `dual` only
# once the site's frontend guard is live (a Hindustani result links to raaga/<slug>.html, which
# does not exist yet, so an un-guarded dual model would 404 the learn link). See DEPLOY.md.
set -euo pipefail
MODEL="${1:-carnatic}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/../.." && pwd)"           # repo root
APP="$HERE/app"

case "$MODEL" in
  carnatic) STEM="raaga_xgb" ;;
  dual)     STEM="raaga_xgb.dual" ;;
  swara)    STEM="raaga_xgb.swara" ;;
  *) echo "usage: assemble.sh [carnatic|dual|swara]"; exit 1 ;;
esac

rm -rf "$APP"; mkdir -p "$APP/models"
cp "$SRC/space/api.py" "$APP/api.py"                 # updated api.py (surfaces tradition)
cp "$SRC/space/requirements-api.txt" "$APP/"
cp -r "$SRC/raaga_id" "$APP/raaga_id"
cp "$SRC/raagas.json" "$SRC/raagas.hindustani.json" "$APP/"   # tradition.py loads the hindustani vocab
cp "$SRC/schema.py" "$SRC/raaga_profiles.json" "$SRC/raaga_guide.json" "$APP/" 2>/dev/null || true
# the chosen model, named raaga_xgb.* so MODEL_PATH=/app/models/raaga_xgb.json picks it up
cp "$SRC/models/$STEM.json"         "$APP/models/raaga_xgb.json"
cp "$SRC/models/$STEM.classes.json" "$APP/models/raaga_xgb.classes.json"
cp "$SRC/models/$STEM.calib.json"   "$APP/models/raaga_xgb.calib.json" 2>/dev/null \
  && echo "bundled calibration ($STEM.calib.json)" || echo "(no calib sidecar for $STEM — runs uncalibrated)"
# Without its chains a swara model would serve unfused answers under the fused temperature, so a
# missing file stops the build. (Not `cp && echo`: set -e does not stop inside an && list.)
if [ "$MODEL" = swara ]; then
  [ -f "$SRC/models/$STEM.chain.npz" ] || { echo "missing $STEM.chain.npz (python -m tools.train_swara fit)"; exit 1; }
  cp "$SRC/models/$STEM.chain.npz" "$APP/models/raaga_xgb.chain.npz"
  echo "bundled swara chains"
fi
find "$APP" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "assembled '$MODEL' model into $APP"
python3 - "$APP/models/raaga_xgb.classes.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
print(f"  {len(c)} classes")
PY
