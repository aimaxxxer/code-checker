#!/usr/bin/env bash
# Look for credentials committed into a repo.
# Usage: checks/scan-secrets.sh [dir ...]   (defaults to the current directory)
set -uo pipefail
dirs=("${@:-.}")
EX=(--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.obsidian
    --exclude-dir=dist --exclude-dir=build --exclude-dir=venv --exclude-dir=.venv)

echo "== key-shaped assignments =="
grep -rInE '(api[_-]?key|secret|token|passwd|password|client[_-]?secret|bearer|private[_-]?key)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][A-Za-z0-9_./+-]{16,}' \
  "${EX[@]}" "${dirs[@]}" 2>/dev/null \
  | grep -viE 'your[_-]?(api)?key|placeholder|example|xxx+|<[a-z_]+>|\$\{|process\.env|os\.environ|getenv|changeme|dummy|replace|test[_-]?key'

echo "== known provider key formats =="
grep -rInE '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|AIza[A-Za-z0-9_-]{30,}|AKIA[A-Z0-9]{16}|xox[baprs]-[A-Za-z0-9-]{10,})' \
  "${EX[@]}" "${dirs[@]}" 2>/dev/null

echo "== credential-ish files tracked by git =="
for d in "${dirs[@]}"; do
  for r in "$d"/*/ "$d"; do
    [ -d "$r/.git" ] || continue
    git -C "$r" ls-files 2>/dev/null \
      | grep -iE '(^|/)(\.env$|.*\.pem$|.*\.key$|.*credential.*|.*secret.*|tokens?\.json$|config\.json$)' \
      | sed "s|^|  $r |"
  done
done

echo "== runtime state tracked by git (churn, and sqlite side files leak rows) =="
for d in "${dirs[@]}"; do
  for r in "$d"/*/ "$d"; do
    [ -d "$r/.git" ] || continue
    git -C "$r" ls-files 2>/dev/null \
      | grep -iE '\.(db|sqlite3?|db-wal|db-shm|db-journal|pid|lock)$' \
      | sed "s|^|  $r |"
  done
done
