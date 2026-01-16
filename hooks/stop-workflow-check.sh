#!/bin/bash
# Hook: stop-workflow-check.sh
# Purpose: Verify workflow completion and OUTPUT relevant instructions before exit

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
LEARNING_CONFIG="$CWD/.claude/learning.json"
INSTRUCTIONS_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/instructions"
REFERENCES_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/references"

# Helper to output instruction file
output_instructions() {
    local STATE="$1"
    local FILE="$INSTRUCTIONS_DIR/$STATE.md"
    if [ -f "$FILE" ]; then
        echo "" >&2
        echo "════════════════════════════════════════════════════════════" >&2
        echo "INSTRUCTIONS ($STATE):" >&2
        echo "════════════════════════════════════════════════════════════" >&2
        cat "$FILE" >&2
        echo "════════════════════════════════════════════════════════════" >&2
    fi
}

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
    "WF_DONE")
        if [ "$LEARNING_MANDATORY" = "true" ] && [ "$LEARNING_COMPLETE" != "true" ]; then
            echo "" >&2
            echo "╔══════════════════════════════════════════════════════════════╗" >&2
            echo "║  ⛔ BLOCKED: RLVR learning checkpoint required               ║" >&2
            echo "╚══════════════════════════════════════════════════════════════╝" >&2
            output_instructions "WF_DONE"
            exit 2
        fi
        REWARD=$(jq -r '.computed_reward // "N/A"' "$STATE_FILE" 2>/dev/null)
        echo "" >&2
        echo "✅ Workflow complete (learning: $LEARNING_COMPLETE, reward: $REWARD)" >&2
        exit 0
        ;;
    "WF_CLEANUP")
        echo "" >&2
        echo "🧹 Workflow cleanup in progress..." >&2
        output_instructions "WF_CLEANUP"
        exit 0
        ;;
    "WF_CLARIFY")
        echo "" >&2
        echo "❓ Paused at WF_CLARIFY - awaiting user clarification" >&2
        output_instructions "WF_CLARIFY"
        exit 0
        ;;
    "WF_ASK_PERMISSION")
        echo "" >&2
        echo "🔐 Paused at WF_ASK_PERMISSION - awaiting user approval" >&2
        output_instructions "WF_ASK_PERMISSION"
        exit 0
        ;;
    "UNINITIALIZED")
        exit 0
        ;;
    *)
        echo "" >&2
        echo "⚠️  INCOMPLETE: Currently at $CURRENT_STATE" >&2
        echo "Update WORKING_MEMORY before stopping." >&2
        output_instructions "$CURRENT_STATE"

        # OUTPUT REF_WORKING_MEMORY for format reference
        REF_WM="$REFERENCES_DIR/REF_WORKING_MEMORY.md"
        if [ -f "$REF_WM" ]; then
            echo "" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "REFERENCE: WORKING_MEMORY FORMAT (from REF_WORKING_MEMORY.md):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$REF_WM" >&2
            echo "════════════════════════════════════════════════════════════" >&2
        fi
        exit 1
        ;;
esac
