#!/usr/bin/env bash
# start-factory.sh — start the software factory on the repo this is called from.
#
# Starts a fresh headless herdr server and runs the deterministic orchestrator against
# the impl tickets at .scratch/<effort>/impl/*.md. Foreground: you see the cycle
# outcomes + stdin gates live; on exit the herdr server is stopped.
#
# Usage (from the repo root, or anywhere under it):
#   ./start-factory.sh [effort] [--pr-stage on|off] [--env-hint TEXT]
#                      [--session NAME] [--cycle-cap N] [--mock] [--no-approve]
#
#   effort       effort slug under .scratch/ (default: the repo directory name)
#   --pr-stage   on|off (default off; off = throwaway smoke, no GitHub PR)
#   --env-hint   repo-specific test-runner hint injected into the implementer prompt
#                (default: the python pytest+hypothesis hint; the orchestrator symlinks
#                the repo's .venv into each worktree)
#   --session    herdr session name (default: factory-<timestamp>, fresh per run)
#   --cycle-cap  cycle ceiling (default 5)
#   --mock       deterministic stubs — no herdr server, no live models (dry run)
#   --no-approve pass --approve to worker pi panes (default on for autonomous runs)
#
# Prereqs (one-time, "step 0"): .venv with ruff/black/pytest/mypy/coverage/pyyaml/
# hypothesis; herdr on PATH + `herdr integration install pi`; models in ~/.pi/agent/
# models.json; impl tickets produced by `/skill:factory-to-tickets <decision>`.
set -euo pipefail

# ---- resolve locations (the repo this script is called from) ----
REPO="$(git -C "${PWD}" rev-parse --show-toplevel)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$SCRIPT_DIR/factory/orchestrator"
PY="$SCRIPT_DIR/.venv/bin/python"
export PATH="$HOME/.local/bin:$PATH"

# ---- defaults ----
EFFORT="$(basename "$REPO")"
PR_STAGE="off"
SESSION="factory-$(date +%s)"
CYCLE_CAP=""
MOCK=0
APPROVE="--no-approve"
ENV_HINT="Tests use pytest + hypothesis; run them with .venv/bin/python -m pytest (a .venv symlink to the main repo is in the worktree root). Stay within scope_files."

# ---- parse args ----
while [ $# -gt 0 ]; do
  case "$1" in
    --pr-stage)    PR_STAGE="$2"; shift 2;;
    --env-hint)    ENV_HINT="$2"; shift 2;;
    --session)     SESSION="$2"; shift 2;;
    --cycle-cap)   CYCLE_CAP="$2"; shift 2;;
    --mock)        MOCK=1; shift;;
    --no-approve)  APPROVE="--no-approve"; shift;;
    --no-approve-off) APPROVE=""; shift;;   # if you want pi's trust prompt to fire
    -h|--help)     awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0;;
    -*)            echo "unknown flag: $1" >&2; exit 2;;
    *)             EFFORT="$1"; shift;;
  esac
done

# ---- prereq checks ----
[ -x "$PY" ] || { echo "ERR: no venv python at $PY — run step 0 (.venv + pip install)" >&2; exit 1; }
[ -d "$ORCH" ] || { echo "ERR: orchestrator not found at $ORCH" >&2; exit 1; }
command -v herdr >/dev/null || { echo "ERR: herdr not on PATH — export PATH=\"\$HOME/.local/bin:\$PATH\"" >&2; exit 1; }

IMPL_GLOB="$REPO/.scratch/$EFFORT/impl/*.md"
if ! ls $IMPL_GLOB >/dev/null 2>&1; then
  echo "ERR: no impl tickets at $IMPL_GLOB" >&2
  echo "     Produce them first: in a pi session on glm-5.2:cloud, run" >&2
  echo "       /skill:factory-to-tickets <resolved-decision-ref>" >&2
  echo "     then commit them to main (the orchestrator worktrees off main)." >&2
  exit 1
fi

WORKTREE_PARENT="$(dirname "$REPO")"
RUN_LOG="/tmp/sf-$SESSION.log"

# ---- build the orchestrator argv ----
ARGS=(
  "$EFFORT"
  --repo "$REPO"
  --pr-stage "$PR_STAGE"
  $APPROVE
  --worktree-parent "$WORKTREE_PARENT"
  --implementer-env-hint "$ENV_HINT"
)
[ -z "$CYCLE_CAP" ] || ARGS+=(--cycle-cap "$CYCLE_CAP")

# ---- mock mode: no herdr, just stubs ----
if [ "$MOCK" -eq 1 ]; then
  echo ">> mock mode (deterministic stubs, no herdr/models)"
  cd "$ORCH" && exec "$PY" -m cli "${ARGS[@]}" --mock
fi

# ---- real mode: start a fresh headless herdr server ----
ARGS+=(--herdr-session "$SESSION")

echo ">> starting headless herdr server (session $SESSION)…"
setsid herdr --session "$SESSION" server >"/tmp/herdr-$SESSION.log" 2>&1 < /dev/null &
HERDR_PID=$!
cleanup() {
  echo ">> stopping herdr server (session $SESSION)…"
  herdr --session "$SESSION" server stop >/dev/null 2>&1 || true
}
trap cleanup EXIT

# wait for the socket
for _ in $(seq 1 20); do
  [ -S "$HOME/.config/herdr/sessions/$SESSION/herdr.sock" ] && break
  sleep 0.5
done
if ! [ -S "$HOME/.config/herdr/sessions/$SESSION/herdr.sock" ]; then
  echo "ERR: herdr server socket did not appear — see /tmp/herdr-$SESSION.log" >&2
  exit 1
fi
echo ">> herdr server up (socket ok). Log: /tmp/herdr-$SESSION.log"
echo ">> watch the sidebar: herdr --session $SESSION   (in another terminal)"
echo ">> orchestrator log: $RUN_LOG"
echo ">> starting orchestrator (foreground). Ctrl-C to stop."
echo

cd "$ORCH"
# Foreground so you can answer stdin gates; tee captures the live log.
"$PY" -m cli "${ARGS[@]}" 2>&1 | tee "$RUN_LOG"