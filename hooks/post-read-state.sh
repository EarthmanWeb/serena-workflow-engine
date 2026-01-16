#!/bin/bash
# Hook: post-read-state.sh
# Purpose: Output step reports, enforce WORKING_MEMORY, track state transitions

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
MEMORY_NAME=$(echo "$INPUT" | jq -r '.tool_input.memory_file_name // empty')
STATE_FILE="$CWD/.claude/workflow-state.json"
INSTRUCTIONS_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/instructions"
REFERENCES_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/references"

[ -z "$MEMORY_NAME" ] && exit 0

# ═══════════════════════════════════════════════════════════════
# STATE ICONS (from states.json)
# ═══════════════════════════════════════════════════════════════
get_state_icon() {
    case "$1" in
        WF_START) echo "🚀" ;;
        WF_CLASSIFY) echo "🔍" ;;
        WF_CONTINUE) echo "▶️" ;;
        WF_RESEARCH) echo "🔬" ;;
        WF_DETECT_REQ) echo "📋" ;;
        WF_REQUIREMENT) echo "📝" ;;
        WF_PLAN_ARCHITECTURE) echo "🏗️" ;;
        WF_ARCH_REVIEW) echo "🔎" ;;
        WF_SWARM_ORCHESTRATE) echo "🐝" ;;
        WF_CLARIFY) echo "❓" ;;
        WF_ASK_PERMISSION) echo "🔐" ;;
        WF_LOAD_FEATURE) echo "📦" ;;
        WF_UPDATE_MEMORY) echo "💾" ;;
        WF_EXECUTE) echo "⚡" ;;
        WF_CHECKPOINT) echo "💾" ;;
        WF_DEBUG_TDD) echo "🐛" ;;
        WF_VERIFY) echo "✔️" ;;
        WF_DONE) echo "✅" ;;
        WF_CLEANUP) echo "🧹" ;;
        WF_ONBOARD) echo "📝" ;;
        WF_INITIAL_SETUP) echo "🔧" ;;
        *) echo "📍" ;;
    esac
}

# ═══════════════════════════════════════════════════════════════
# HANDLE WF_* STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════
if [[ "$MEMORY_NAME" == WF_* ]]; then
    ICON=$(get_state_icon "$MEMORY_NAME")

    # ═══════════════════════════════════════════════════════════════
    # STEP REPORT BANNER (ALWAYS OUTPUT)
    # ═══════════════════════════════════════════════════════════════
    echo "" >&2
    echo "════════════════════════════════════════════════════════════" >&2
    echo "$ICON ON STEP: $MEMORY_NAME" >&2
    echo "════════════════════════════════════════════════════════════" >&2

    # If no state file, warn but continue
    if [ ! -f "$STATE_FILE" ]; then
        echo "" >&2
        echo "⚠️  No workflow state file. Run /swe-init or session-start hook." >&2
        echo "" >&2
        exit 1
    fi

    CURRENT=$(jq -r '.current_state' "$STATE_FILE" 2>/dev/null)
    WM_FILE=$(jq -r '.working_memory_file // empty' "$STATE_FILE" 2>/dev/null)
    TRAJ_ID=$(jq -r '.trajectory_id // empty' "$STATE_FILE" 2>/dev/null)
    CURRENT_PLAN_MODE=$(jq -r '.plan_mode // false' "$STATE_FILE" 2>/dev/null)

    # ═══════════════════════════════════════════════════════════════
    # WORKING_MEMORY ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════
    if [ -z "$WM_FILE" ] && [ "$MEMORY_NAME" != "WF_INITIAL_SETUP" ] && [ "$MEMORY_NAME" != "WF_ONBOARD" ]; then
        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  ⚠️  WORKING_MEMORY REQUIRED                                  ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        echo "You MUST create a WORKING_MEMORY file before proceeding." >&2
        echo "" >&2
        echo "CREATE NOW:" >&2
        echo "  mcp__serena__write_memory(\"WORKING_MEMORY_YYYYMMDD_descriptor\", content)" >&2
        echo "" >&2
        echo "Example: WORKING_MEMORY_20260116_fix_auth_bug" >&2
        echo "" >&2

        # OUTPUT REF_WORKING_MEMORY for format reference
        REF_WM="$REFERENCES_DIR/REF_WORKING_MEMORY.md"
        if [ -f "$REF_WM" ]; then
            echo "════════════════════════════════════════════════════════════" >&2
            echo "REFERENCE: WORKING_MEMORY FORMAT (from REF_WORKING_MEMORY.md):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$REF_WM" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "" >&2
        fi
    fi

    # Show transition
    echo "Transition: $CURRENT → $MEMORY_NAME" >&2

    # RLVR: Increment state transition counter and trajectory steps
    jq '.reward_signals.state_transitions += 1 | .trajectory_steps += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    # RLVR: Track clarify visits as penalty
    if [ "$MEMORY_NAME" = "WF_CLARIFY" ]; then
        jq '.reward_signals.clarify_count += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    fi

    # RLVR: Track arch review pass
    if [ "$MEMORY_NAME" = "WF_EXECUTE" ] && [ "$CURRENT" = "WF_ARCH_REVIEW" ]; then
        jq '.reward_signals.arch_review_pass = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    fi

    # RLVR: Track verify success
    if [ "$MEMORY_NAME" = "WF_DONE" ] && [ "$CURRENT" = "WF_VERIFY" ]; then
        jq '.reward_signals.verify_success = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    fi

    # ═══════════════════════════════════════════════════════════════
    # AUTO PLAN MODE SWITCHING
    # ═══════════════════════════════════════════════════════════════
    PLAN_MODE_ALWAYS="WF_PLAN_ARCHITECTURE WF_ARCH_REVIEW WF_SWARM_ORCHESTRATE"
    PLAN_MODE_NEVER="WF_DEBUG_TDD WF_CHECKPOINT WF_VERIFY WF_DONE WF_CLEANUP WF_RESEARCH WF_EXECUTE"

    NEW_PLAN_MODE="$CURRENT_PLAN_MODE"
    PLAN_REASON=""

    if echo "$PLAN_MODE_ALWAYS" | grep -qw "$MEMORY_NAME"; then
        if [ "$CURRENT_PLAN_MODE" != "true" ]; then
            NEW_PLAN_MODE="true"
            PLAN_REASON="State $MEMORY_NAME requires architecture planning"
            jq '.plan_mode_entries += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

            echo "" >&2
            echo "╔══════════════════════════════════════════════════════════════╗" >&2
            echo "║  📋 ENTERING PLAN MODE - Architecture/Planning Required      ║" >&2
            echo "╚══════════════════════════════════════════════════════════════╝" >&2
            echo "" >&2
            echo "ACTION REQUIRED: Call EnterPlanMode() tool now." >&2
            echo "" >&2
        fi
    elif echo "$PLAN_MODE_NEVER" | grep -qw "$MEMORY_NAME"; then
        if [ "$CURRENT_PLAN_MODE" = "true" ]; then
            NEW_PLAN_MODE="false"
            PLAN_REASON="State $MEMORY_NAME is execution/verification (no planning)"

            echo "" >&2
            echo "╔══════════════════════════════════════════════════════════════╗" >&2
            echo "║  ⚡ EXITING PLAN MODE - Entering Execution/Debug             ║" >&2
            echo "╚══════════════════════════════════════════════════════════════╝" >&2
            echo "" >&2
        fi
    fi

    # Update state
    jq --arg new "$MEMORY_NAME" --arg old "$CURRENT" --argjson pm "$NEW_PLAN_MODE" --arg reason "$PLAN_REASON" \
        '.previous_state = $old | .current_state = $new | .plan_mode = $pm | .plan_mode_reason = $reason' \
        "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    # Reset edit counter on checkpoint
    [ "$MEMORY_NAME" = "WF_CHECKPOINT" ] && jq '.edits_since_checkpoint = 0' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    echo "" >&2
    exit 1
fi

# ═══════════════════════════════════════════════════════════════
# HANDLE WORKING_MEMORY_* READS
# ═══════════════════════════════════════════════════════════════
if [[ "$MEMORY_NAME" == WORKING_MEMORY_* ]]; then
    if [ -f "$STATE_FILE" ]; then
        jq --arg wm "$MEMORY_NAME" '.working_memory_file = $wm | .edits_since_checkpoint = 0' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        echo "" >&2
        echo "📋 Working Memory: $MEMORY_NAME" >&2
        echo "" >&2
        exit 1
    fi
fi

exit 0
