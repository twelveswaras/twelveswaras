#!/bin/bash
# Assemble a deployable Hugging Face Space in ./space_build from this repo, bundling the
# trained model. Then push space_build/ to the Space git repo.
set -e
SRC="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$SRC/space_build"

rm -rf "$OUT"
mkdir -p "$OUT/models"
cp -r "$SRC/raaga_id" "$SRC/apps" "$SRC/assets" "$OUT/"
cp "$SRC/schema.py" "$SRC/raagas.json" "$OUT/"
cp "$SRC/raaga_profiles.json" "$SRC/raaga_guide.json" "$OUT/"   # learner-panel data
cp "$SRC/models/raaga_xgb.json" "$SRC/models/raaga_xgb.classes.json" "$OUT/models/"
cp "$SRC/space/app.py" "$SRC/space/requirements.txt" "$SRC/space/packages.txt" "$SRC/space/README.md" "$OUT/"
find "$OUT" -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "Assembled HF Space in: $OUT"
echo
echo "Deploy (after 'huggingface-cli login' and creating the Space):"
echo "  cd \"$OUT\""
echo "  git init && git add -A && git commit -m 'twelveswaras recognizer'"
echo "  git remote add origin https://huggingface.co/spaces/twelveswaras/twelveswaras"
echo "  git push -u origin main"
