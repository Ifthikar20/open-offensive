#!/usr/bin/env bash
#
# OpenOffensive installer — puts the `openoffensive` CLI on your PATH.
#
#   curl -sSL https://raw.githubusercontent.com/Ifthikar20/open-offensive/clean-main/install.sh | bash
#
# Environment knobs (all optional):
#   OPENOFFENSIVE_REF=clean-main     git ref (branch/tag) to install from
#   OPENOFFENSIVE_NO_LLM=1           install the zero-dependency core only (skip the LLM extra)
#   OPENOFFENSIVE_METHOD=pipx|pip    force the install method (default: pipx if present, else pip --user)
#
set -euo pipefail

REPO_URL="https://github.com/Ifthikar20/open-offensive"
REF="${OPENOFFENSIVE_REF:-clean-main}"

# ---- pretty output --------------------------------------------------------
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; PURPLE=$'\033[35m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YELLOW=""; PURPLE=""; RESET=""
fi
say()  { printf '%s\n' "$*"; }
info() { printf '%s▸%s %s\n' "$PURPLE" "$RESET" "$*"; }
ok()   { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*" >&2; }
die()  { printf '%s✗ %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

say ""
say "${BOLD}${PURPLE}OpenOffensive${RESET} — the open-source AI pentester"
say "${DIM}installing the 'openoffensive' CLI${RESET}"
say ""

# ---- 1. Python ------------------------------------------------------------
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || die "Python 3.9+ is required but no python3 was found. Install Python and re-run."

PYV=$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)'; then
  die "Python 3.9+ is required (found $PYV). Please upgrade Python and re-run."
fi
ok "Python $PYV detected ($PY)"

# ---- 2. what to install ---------------------------------------------------
# The engine core is pure standard library. The [llm] extra adds the model client
# the AI agents reason with (required to run a scan). We install it by default.
if [ "${OPENOFFENSIVE_NO_LLM:-}" = "1" ]; then
  SPEC="git+${REPO_URL}.git@${REF}"
  EXTRA_NOTE="core only (no model client; scans need the [llm] extra + a key)"
else
  SPEC="openoffensive[llm] @ git+${REPO_URL}.git@${REF}"
  EXTRA_NOTE="with the LLM extra"
fi

# If we're being run from inside a checkout, install that instead of the remote.
if [ -f "./pyproject.toml" ] && grep -q '^name = "openoffensive"' ./pyproject.toml 2>/dev/null; then
  if [ "${OPENOFFENSIVE_NO_LLM:-}" = "1" ]; then SPEC="."; else SPEC=".[llm]"; fi
  info "Installing from the local checkout ($EXTRA_NOTE)…"
else
  info "Installing from ${REPO_URL} @ ${REF} ($EXTRA_NOTE)…"
fi

# ---- 3. install method ----------------------------------------------------
METHOD="${OPENOFFENSIVE_METHOD:-}"
if [ -z "$METHOD" ]; then
  if command -v pipx >/dev/null 2>&1; then METHOD="pipx"; else METHOD="pip"; fi
fi

case "$METHOD" in
  pipx)
    command -v pipx >/dev/null 2>&1 || die "OPENOFFENSIVE_METHOD=pipx but pipx is not installed."
    pipx install --force "$SPEC"
    pipx ensurepath >/dev/null 2>&1 || true
    ;;
  pip)
    # Isolated apps are cleaner via pipx; fall back to a user install of pip.
    if ! "$PY" -m pip --version >/dev/null 2>&1; then
      die "pip is not available for $PY. Install pip (or pipx) and re-run.
     Debian/Ubuntu: sudo apt install python3-pip pipx
     macOS:         brew install pipx"
    fi
    if ! "$PY" -m pip install --user --upgrade "$SPEC" 2>/tmp/oo_pip_err; then
      if grep -qi "externally-managed-environment" /tmp/oo_pip_err 2>/dev/null; then
        rm -f /tmp/oo_pip_err
        die "This Python is externally managed (PEP 668), so a plain pip --user install is blocked.
     Install pipx and re-run — it isolates the CLI cleanly:
       Debian/Ubuntu: sudo apt install pipx && pipx ensurepath
       macOS:         brew install pipx && pipx ensurepath
     Then: curl -sSL ${REPO_URL}/raw/${REF}/install.sh | bash"
      fi
      cat /tmp/oo_pip_err >&2; rm -f /tmp/oo_pip_err
      die "pip install failed (see the error above)."
    fi
    rm -f /tmp/oo_pip_err
    ;;
  *)
    die "Unknown OPENOFFENSIVE_METHOD='$METHOD' (use 'pipx' or 'pip')."
    ;;
esac

# ---- 4. locate the CLI + PATH check --------------------------------------
BIN=""
if command -v openoffensive >/dev/null 2>&1; then
  BIN="$(command -v openoffensive)"
else
  # common user-bin locations for pipx / pip --user
  USER_BASE="$("$PY" -m site --user-base 2>/dev/null || echo "$HOME/.local")"
  for d in "$HOME/.local/bin" "$USER_BASE/bin"; do
    if [ -x "$d/openoffensive" ]; then BIN="$d/openoffensive"; break; fi
  done
fi

[ -n "$BIN" ] || die "Installed, but the 'openoffensive' command could not be located on disk.
     Check your Python user bin directory and add it to PATH."

VER="$("$BIN" --version 2>/dev/null || echo 'openoffensive')"
ok "Installed: ${BOLD}${VER}${RESET}"

BINDIR="$(dirname "$BIN")"
case ":$PATH:" in
  *":$BINDIR:"*) : ;;
  *)
    warn "$BINDIR is not on your PATH. Add it (then restart your shell):"
    say  "    ${BOLD}export PATH=\"$BINDIR:\$PATH\"${RESET}"
    ;;
esac

# ---- 5. next steps --------------------------------------------------------
say ""
say "${BOLD}Next steps${RESET}"
say "  ${DIM}# 1. point the AI agents at a model (required — they reason with it)${RESET}"
say "  export ANTHROPIC_API_KEY=\"your-api-key\""
say ""
say "  ${DIM}# 2. run your first assessment (authorized targets only)${RESET}"
say "  openoffensive scan https://example.com            # a live URL"
say "  openoffensive scan https://github.com/org/repo    # a git repo"
say "  openoffensive serve https://example.com           # live dashboard"
say ""
say "  ${DIM}# no Docker / locked-down network? run tools on the host:${RESET}"
say "  OPENOFFENSIVE_SANDBOX=local openoffensive scan https://example.com"
say ""
ok  "Done. Happy hunting — ${DIM}authorized targets only.${RESET}"
say ""
