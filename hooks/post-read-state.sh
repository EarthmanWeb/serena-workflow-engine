#!/bin/bash
# Hook: post-read-state.sh
# Purpose: Track state transitions, RLVR signals, and auto plan mode switching

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
MEMORY_NAME=$(echo "$INPUT" | jq -r '.tool_input.memory_file_name // empty')
STATE_FILE="$CWD/.claude/workflow-state.json"

[ -z "$MEMORY_NAME" ] && exit 0
[ ! -f "$STATE_FILE" ] && exit 0

# Handle WF_* state transitions
if [[ "$MEMORY_NAME" == WF_* ]]; then
    CURRENT=$(jq -r '.current_state' "$STATE_FILE" 2>/dev/null)
    TRAJ_ID=$(jq -r '.trajectory_id // empty' "$STATE_FILE" 2>/dev/null)
    CURRENT_PLAN_MODE=$(jq -r '.plan_mode // false' "$STATE_FILE" 2>/dev/null)

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

    # States that ALWAYS require Plan Mode
    PLAN_MODE_ALWAYS="WF_PLAN_ARCHITECTURE WF_ARCH_REVIEW WF_SWARM_ORCHESTRATE"

    # States that NEVER use Plan Mode (bypass)
    PLAN_MODE_NEVER="WF_DEBUG_TDD WF_CHECKPOINT WF_VERIFY WF_DONE WF_CLEANUP WF_RESEARCH WF_EXECUTE"

    NEW_PLAN_MODE="$CURRENT_PLAN_MODE"
    PLAN_REASON=""

    # Check if new state requires plan mode
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
            echo "Reason: $PLAN_REASON" >&2
            echo "" >&2
            echo "ACTION REQUIRED: Call EnterPlanMode() tool now." >&2
            echo "  - Write plan to plan file" >&2
            echo "  - Present options to user" >&2
            echo "  - Wait for approval via ExitPlanMode()" >&2
            echo "" >&2
        fi

    # Check if new state should exit plan mode
    elif echo "$PLAN_MODE_NEVER" | grep -qw "$MEMORY_NAME"; then
        if [ "$CURRENT_PLAN_MODE" = "true" ]; then
            NEW_PLAN_MODE="false"
            PLAN_REASON="State $MEMORY_NAME is execution/verification (no planning)"

            echo "" >&2
            echo "╔══════════════════════════════════════════════════════════════╗" >&2
            echo "║  ⚡ EXITING PLAN MODE - Entering Execution/Debug             ║" >&2
            echo "╚══════════════════════════════════════════════════════════════╝" >&2
            echo "" >&2
            echo "Reason: $PLAN_REASON" >&2
            echo "Proceeding in Agent Mode (direct execution)." >&2
            echo "" >&2
        fi
    fi

    # Update state with plan mode
    jq --arg new "$MEMORY_NAME" --arg old "$CURRENT" --argjson pm "$NEW_PLAN_MODE" --arg reason "$PLAN_REASON" \
        '.previous_state = $old | .current_state = $new | .plan_mode = $pm | .plan_mode_reason = $reason' \
        "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    # RLVR: Emit trajectory step
    if [ -n "$TRAJ_ID" ]; then
        QUALITY=1.0
        [ "$MEMORY_NAME" = "WF_CLARIFY" ] && QUALITY=0.7
    fi

    # Reset edit counter on checkpoint
    [ "$MEMORY_NAME" = "WF_CHECKPOINT" ] && jq '.edits_since_checkpoint = 0' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    echo "STATE: $CURRENT → $MEMORY_NAME (plan_mode=$NEW_PLAN_MODE)" >&2
    exit 1
fi

# Handle WORKING_MEMORY_* reads
if [[ "$MEMORY_NAME" == WORKING_MEMORY_* ]]; then
    jq --arg wm "$MEMORY_NAME" '.working_memory_file = $wm | .edits_since_checkpoint = 0' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
fi

exit 0
