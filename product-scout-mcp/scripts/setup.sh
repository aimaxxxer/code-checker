#!/usr/bin/env bash
# One-shot setup. Installs the server, checks it works, and prints the exact
# config block to paste into Claude. Safe to run more than once.

set -uo pipefail

BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RED=$'\033[31m'; OFF=$'\033[0m'
ok()   { printf "  ${GREEN}OK${OFF}  %s\n" "$1"; }
warn() { printf "  ${YELLOW}!${OFF}   %s\n" "$1"; }
fail() { printf "  ${RED}X${OFF}   %s\n" "$1"; }
step() { printf "\n${BOLD}%s${OFF}\n" "$1"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR" || exit 1

printf "${BOLD}Product Scout setup${OFF}\n%s\n" "$PROJECT_DIR"

# ---------------------------------------------------------------- 1. Python
step "1. Checking Python"
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        version="$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
        if [ -n "$version" ] && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
            PY="$candidate"; ok "Python $version ($(command -v "$candidate"))"; break
        fi
    fi
done
if [ -z "$PY" ]; then
    fail "Python 3.10 or newer was not found."
    echo "      Install it from https://www.python.org/downloads/ then run this again."
    exit 1
fi

# ------------------------------------------------------------ 2. Environment
step "2. Building the environment (this can take a minute)"
if command -v uv >/dev/null 2>&1; then
    uv venv --quiet 2>/dev/null || true
    if uv pip install --quiet -e "." 2>/dev/null; then
        ok "Installed with uv"
    else
        fail "uv install failed — falling back to pip"
        rm -rf .venv
        "$PY" -m venv .venv && .venv/bin/python -m pip install --quiet --upgrade pip && \
            .venv/bin/python -m pip install --quiet -e "." && ok "Installed with pip"
    fi
else
    [ -d .venv ] || "$PY" -m venv .venv
    .venv/bin/python -m pip install --quiet --upgrade pip 2>/dev/null
    if .venv/bin/python -m pip install --quiet -e "." 2>/dev/null; then
        ok "Installed with pip"
    else
        fail "Install failed. Check your internet connection and try again."
        exit 1
    fi
fi

VENV_PY="$PROJECT_DIR/.venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$PROJECT_DIR/.venv/Scripts/python.exe"   # Windows layout
if [ ! -x "$VENV_PY" ]; then
    fail "Could not find the Python inside .venv — setup did not complete."
    exit 1
fi

# ------------------------------------------------------------------ 3. Keys
step "3. Checking your API keys"
if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from the template"
else
    ok ".env already exists (left alone)"
fi

has_key() { grep -qE "^$1=.+" .env 2>/dev/null; }
KEYS_SET=0
if has_key SERPAPI_KEY; then ok "SERPAPI_KEY is set — real prices and trends"; KEYS_SET=1
else warn "SERPAPI_KEY is empty — margins will be guesses, not measurements"; fi
if has_key ALIEXPRESS_APP_KEY && has_key ALIEXPRESS_APP_SECRET; then ok "AliExpress keys are set — real product data"; KEYS_SET=1
else warn "AliExpress keys are empty — using demo products"; fi
if has_key APIFY_TOKEN; then ok "APIFY_TOKEN is set — Temu and Alibaba available"; fi
[ "$KEYS_SET" -eq 0 ] && warn "No keys yet. It still runs, on clearly-labelled fake data."

# ------------------------------------------------------------------ 4. Test
step "4. Testing that it works"
if "$VENV_PY" scripts/smoke.py >/tmp/ps_smoke.log 2>&1; then
    ok "The server ran and produced a ranked shortlist"
else
    fail "The test run failed. Full output:"
    tail -20 /tmp/ps_smoke.log
    exit 1
fi

# ---------------------------------------------------------------- 5. Config
step "5. Connect it to Claude"

case "$(uname -s 2>/dev/null)" in
    Darwin) CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
    MINGW*|MSYS*|CYGWIN*) CONFIG="$APPDATA/Claude/claude_desktop_config.json" ;;
    *) CONFIG="$HOME/.config/Claude/claude_desktop_config.json" ;;
esac

cat > "$PROJECT_DIR/claude-config-snippet.json" <<JSON
{
  "mcpServers": {
    "product-scout": {
      "command": "$VENV_PY",
      "args": ["-m", "product_scout.server"],
      "env": {
        "PRODUCT_SCOUT_MARKET": "US"
      }
    }
  }
}
JSON

echo "  Claude Desktop:"
echo "    Settings -> Developer -> Edit Config, then paste what is in"
echo "    ${BOLD}claude-config-snippet.json${OFF} (written next to this project)."
echo "    That file is usually at:"
echo "      $CONFIG"
echo "    Quit Claude completely and reopen it afterwards."
echo
echo "  Claude Code, instead, run this one line:"
echo "    ${BOLD}claude mcp add product-scout -- \"$VENV_PY\" -m product_scout.server${OFF}"
echo
printf "${GREEN}${BOLD}Setup finished.${OFF}\n"
echo "Then ask Claude: \"Use product scout to find winning products for a pet store in the US.\""
echo
echo "To add keys later: open the .env file in this folder, paste them in, save,"
echo "and restart Claude. Run scripts/setup.sh again any time to re-check."
