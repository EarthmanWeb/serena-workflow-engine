#!/bin/bash
# Hook: stop-workflow-check.sh
# Purpose: Verify workflow completion and RLVR learning before session end

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
LEARNING_CONFIG="$CWD/.claude/learning.json"

[ ! -f "$STATE_FILE" ] && exit 0

IS_SWARM=$(jq -r '.is_swarm_agent // false' "$STATE_FILE" 2>/dev/null)
IS_CLAUDE_FLOW=$(jq -r '.is_claude_flow_agent // false' "$STATE_FILE" 2>/dev/null)

# If claude-flow agent, run session-end hook before exiting
if [ "$IS_CLAUDE_FLOW" = "true" ]; then
    if command -v npx &> /dev/null; then
        echo "claude-flow: Ending session..." >&2
        npx claude-flow@alpha hooks session-end \
            --generate-summary true \
            --persist-state true \
            --export-metrics true 2>&1 || true
    fi
    exit 0
fi

[ "$IS_SWARM" = "true" ] && exit 0

CURRENT_STATE=$(jq -r '.current_state // "UNINITIALIZED"' "$STATE_FILE" 2>/dev/null)
LEARNING_COMPLETE=$(jq -r '.learning_complete // false' "$STATE_FILE" 2>/dev/null)
LEARNING_MANDATORY=$(jq -r '.learning.mandatory // true' "$LEARNING_CONFIG" 2>/dev/null)
PLAN_MODE=$(jq -r '.plan_mode // false' "$STATE_FILE" 2>/dev/null)

# Warn if stopping in plan mode
if [ "$PLAN_MODE" = "true" ]; then
    echo "" >&2
    echo "⚠️  WARNING: Stopping while in Plan Mode. Plan may be incomplete." >&2
fi

case "$CURRENT_STATE" in
    "WF_DONE"|"WF_CLEANUP")
        if [ "$LEARNING_MANDATORY" = "true" ] && [ "$LEARNING_COMPLETE" != "true" ]; then
            echo "" >&2
            echo "╔══════════════════════════════════════════════════════════════╗" >&2
            echo "║  ⛔ BLOCKED: RLVR learning checkpoint required               ║" >&2
            echo "╚══════════════════════════════════════════════════════════════╝" >&2
            echo "" >&2
            echo "Execute before completing:" >&2
            echo "  1. trajectory-end" >&2
            echo "  2. SONA learn" >&2
            echo "  3. pattern-store" >&2
            echo "  4. agent-adapt" >&2
            exit 2
        fi
        REWARD=$(jq -r '.computed_reward // "N/A"' "$STATE_FILE" 2>/dev/null)
        echo "" >&2
        echo "✅ Workflow complete (learning: $LEARNING_COMPLETE, reward: $REWARD)" >&2
        exit 0
        ;;
    "WF_CLARIFY"|"WF_ASK_PERMISSION")
        echo "" >&2
        echo "⏸️  Paused at $CURRENT_STATE - awaiting user input" >&2
        exit 0
        ;;
    "UNINITIALIZED")
        exit 0
        ;;
    *)
        echo "" >&2
        echo "⚠️  INCOMPLETE: Currently at $CURRENT_STATE" >&2
        echo "Update WORKING_MEMORY before stopping." >&2
        exit 1
        ;;
esac
