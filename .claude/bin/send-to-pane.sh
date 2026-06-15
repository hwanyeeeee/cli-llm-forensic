#!/usr/bin/env bash
# Send text to a tmux pane and submit, using REAL bracketed paste so the
# Codex TUI's PasteBurst state machine sees an explicit paste end instead
# of inferring one from rapid keystrokes.
#
# Root cause (found via Codex source inspection, openai/codex
# rust-v0.125.0): Codex TUI uses a PasteBurst state machine with an
# Enter-suppress window of ~120ms and a char-active timeout of ~8ms.
# `tmux send-keys -l` injects literal characters into the PTY *without*
# bracketed-paste markers, so Codex must INFER paste from input bursts.
# Under load the inference can keep paste-burst state alive past our
# sleeps, so M-Enter and the trailing Enter land inside the same burst
# and become newlines instead of a submit. Empirical signature:
# manual Enter ~30s later always submits the message that was already
# sitting in the composer.
#
# Fix: `tmux paste-buffer -p` writes the buffer to the PTY wrapped in
# real bracketed-paste markers (\e[200~ ... \e[201~). Codex sees an
# explicit paste boundary and exits burst state cleanly. M-Enter is no
# longer needed: include a trailing newline in the buffer so the cursor
# lands on an empty trailing line, then send a single plain Enter to
# submit (this is the only Enter form Codex accepts as submit).
#
# Tunable: SEND_DELAY=<seconds> (default 1).
#
# Usage: send-to-pane.sh <pane-id> <message>
set -euo pipefail
PANE="${1:?pane-id required}"
MSG="${2:?message required}"
DELAY="${SEND_DELAY:-1}"
BUFFER_NAME="sendpane-$$"

PREV_PANE="$(tmux display-message -p '#{pane_id}' 2>/dev/null || true)"
if [ -n "$PREV_PANE" ] && [ "$PREV_PANE" != "$PANE" ]; then
  tmux select-pane -t "$PANE"
  RESTORE_PANE=1
else
  RESTORE_PANE=0
fi

if [[ "$MSG" != *$'\n' ]]; then
  MSG="${MSG}"$'\n'
fi

tmux set-buffer -b "$BUFFER_NAME" "$MSG"
tmux paste-buffer -t "$PANE" -b "$BUFFER_NAME" -p -d
sleep "$DELAY"
tmux send-keys -t "$PANE" Enter

# Mirror panel 1 dispatches into a stable tmux named buffer so /dev-swap can
# re-deliver context to a replacement tool. Lives in tmux server memory only —
# no filesystem state. Internal sends (tool launch command, role handover) opt
# out via SKIP_DISPATCH_LOG=1 so they don't overwrite the real dispatch.
PANEL1_ID="$(bash "$(dirname "$0")/resolve-pane.sh" panel1 2>/dev/null || cat .harness/panel1.id 2>/dev/null || true)"
if [ -n "$PANEL1_ID" ] && [ "$PANE" = "$PANEL1_ID" ] && [ "${SKIP_DISPATCH_LOG:-0}" != "1" ]; then
  tmux set-buffer -b panel1-last-dispatch "$MSG"
fi

if [ "$RESTORE_PANE" = "1" ]; then
  tmux select-pane -t "$PREV_PANE" 2>/dev/null || true
fi
