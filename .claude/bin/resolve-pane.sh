#!/usr/bin/env bash
# Resolve a harness role (panel0|panel1) to a LIVE tmux pane id — %ID-independent.
#
# Why: tmux pane ids (%N) are volatile. On session resume / tmux server restart /
# window rebuild they get renumbered, so any cached `.harness/panelN.id` goes stale
# and notification routing breaks. This resolver derives the live id from stable
# facts at call time, self-healing across restarts.
#
# Strategy (first hit wins):
#   1) position within the reference pane's WINDOW — 1st pane = panel0, 2nd = panel1
#      (sorted by pane_index; base-index agnostic). The harness window has 2 panes.
#   2) @fa_role user-option tag within the reference pane's SESSION.
#   3) cached .harness/<role>.id (last resort / non-tmux contexts).
#
# Usage: resolve-pane.sh <panel0|panel1> [reference_pane]   (ref default: $TMUX_PANE)
# Prints the pane id; exit 0 if resolved, 1 if not.
set -uo pipefail
ROLE="${1:?role required (panel0|panel1)}"
REF="${2:-${TMUX_PANE:-}}"
ROOT="${CLAUDE_PROJECT_DIR:-.}"
id=""

case "$ROLE" in
  panel0) POS=1 ;;
  panel1) POS=2 ;;
  *) POS=0 ;;
esac

if [ -n "$REF" ] && [ "$POS" -gt 0 ]; then
  WIN="$(tmux display-message -p -t "$REF" '#{window_id}' 2>/dev/null || true)"
  if [ -n "$WIN" ]; then
    # 1) Nth pane of the reference window (sorted by index)
    id="$(tmux list-panes -t "$WIN" -F '#{pane_index} #{pane_id}' 2>/dev/null \
          | sort -n | sed -n "${POS}p" | awk '{print $2}')"
  fi
  # 2) @fa_role tag, scoped to the reference session
  if [ -z "$id" ]; then
    SESS="$(tmux display-message -p -t "$REF" '#{session_name}' 2>/dev/null || true)"
    [ -n "$SESS" ] && id="$(tmux list-panes -s -t "$SESS" -F '#{@fa_role} #{pane_id}' 2>/dev/null \
                            | awk -v r="$ROLE" '$1==r{print $2; exit}')"
  fi
fi

# 3) cached id (non-tmux contexts / fallback)
[ -z "$id" ] && id="$(cat "$ROOT/.harness/$ROLE.id" 2>/dev/null || true)"

if [ -n "$id" ]; then
  printf '%s\n' "$id"
  exit 0
fi
exit 1
