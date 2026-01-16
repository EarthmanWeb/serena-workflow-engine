#!/bin/bash
# Hook: pre-edit-validate.sh
# Purpose: Validate edit permissions based on workflow state and plan mode

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"

# Block if no state file (workflow not initialized)
if [ ! -f "$STATE_FILE" ]; then
    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  ⛔ BLOCKED: Workflow not initialized                        ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "Read WF_START first before making any edits." >&2
    exit 2
fi

CURRENT_STATE=$(jq -r '.current_state' "$STATE_FILE")
IS_SWARM=$(jq -r '.is_swarm_agent // false' "$STATE_FILE")
PLAN_MODE=$(jq -r '.plan_mode // false' "$STATE_FILE")

# Bypass for swarm agents
[ "$IS_SWARM" = "true" ] && exit 0

# Block edits in plan mode (planning only, no execution)
if [ "$PLAN_MODE" = "true" ]; then
    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  ⛔ BLOCKED: Currently in Plan Mode                          ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "Call ExitPlanMode() and get user approval before editing." >&2
    exit 2
fi

# Validate state allows edits
case "$CURRENT_STATE" in
    "WF_EXECUTE"|"WF_CHECKPOINT"|"WF_UPDATE_MEMORY"|"WF_ONBOARD"|"WF_DEBUG_TDD"|"WF_INITIAL_SETUP")
        # Increment edit counter
        jq '.edits_since_checkpoint += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        exit 0
        ;;
    "UNINITIALIZED")
        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  ⛔ BLOCKED: Workflow not started                            ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        echo "Read WF_START first." >&2
        exit 2
        ;;
    *)
        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  ⛔ BLOCKED: State $CURRENT_STATE does not allow edits" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        echo "Valid edit states: WF_EXECUTE, WF_CHECKPOINT, WF_DEBUG_TDD" >&2
        exit 2
        ;;
esac
