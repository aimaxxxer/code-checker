#!/usr/bin/env bash
# Parse every source file in every repo under the given directory.
# Catches nothing subtle, but catches everything that cannot possibly run.
# Usage: checks/check-syntax.sh [dir]   (defaults to the current directory)
set -uo pipefail
ROOT="${1:-.}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0

find_src() {
  find "$ROOT" -type f "$@" \
    -not -path '*/.git/*' -not -path '*/node_modules/*' -not -path '*/venv/*' \
    -not -path '*/.venv/*' -not -path '*/dist/*' -not -path '*/build/*' \
    -not -path '*/__pycache__/*' -not -path '*/.obsidian/*' -not -path '*/vendor/*' 2>/dev/null
}

echo "== python =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! out=$(python3 -m py_compile "$f" 2>&1); then
    echo "  SYNTAX $f"; echo "$out" | sed 's/^/    /'; fail=1
  fi
done < <(find_src -name '*.py')

echo "== javascript =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  node --check "$f" >/dev/null 2>&1 && continue
  # may legitimately be an ES module
  node --input-type=module --check < "$f" >/dev/null 2>&1 && continue
  echo "  SYNTAX $f"; node --check "$f" 2>&1 | head -3 | sed 's/^/    /'; fail=1
done < <(find_src -name '*.js' -o -name '*.cjs' -o -name '*.mjs')

echo "== inline <script> in html =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  node "$HERE/check-inline-scripts.js" "$f" || fail=1
done < <(find_src -name '*.html')

echo "== shell =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  bash -n "$f" 2>&1 | sed 's/^/  /'
done < <(find_src -name '*.sh' -o -name '*.command' -o -name '*.bash')

echo "== broken local src/href in html =="
while IFS= read -r f; do
  [ -n "$f" ] || continue
  node "$HERE/dead-refs.js" "$f"
done < <(find_src -name '*.html')

exit $fail
