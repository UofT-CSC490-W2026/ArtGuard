#!/usr/bin/env bash
# Shared color definitions and output helpers for ArtGuard scripts.
#
# Source this at the top of any script:
#   source "$(dirname "$0")/_colors.sh"
#
# Provides:
#   Colors:  RED, GREEN, YELLOW, BLUE, CYAN, BOLD, DIM, NC (reset)
#   Helpers: info(), success(), warn(), error(), step(), header()
#   Tools:   require_tool() — exits with a clear message if a CLI tool is missing

# ─── Color codes (disabled when piped or in CI) ──────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  BOLD='\033[1m'
  DIM='\033[2m'
  NC='\033[0m'  # No Color / Reset
else
  # Non-interactive (piped, CI logs) — no ANSI codes
  RED='' GREEN='' YELLOW='' BLUE='' CYAN='' BOLD='' DIM='' NC=''
fi

# ─── Print helpers ────────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
step()    { echo -e "${CYAN}[STEP]${NC}  ${BOLD}$*${NC}"; }
header()  {
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BOLD}  $*${NC}"
  echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ─── Tool validation ──────────────────────────────────────────────────────────
# Usage: require_tool terraform aws docker jq
# Exits with a descriptive error if any tool is not on PATH.
require_tool() {
  for tool in "$@"; do
    if ! command -v "$tool" &>/dev/null; then
      error "Required tool not found: ${BOLD}$tool${NC}"
      echo -e "  ${DIM}Install it and make sure it is on your PATH, then retry.${NC}"
      exit 1
    fi
  done
}
