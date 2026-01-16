#!/bin/bash
# Hook: post-edit-checkpoint.sh
# Purpose: Track edits and enforce checkpoint after 3 edits

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.relative_path // empty')

[ ! -f "$STATE_FILE" ] && exit 0

IS_SWARM=$(jq -r '.is_swarm_agent // false' "$STATE_FILE" 2>/dev/null)
[ "$IS_SWARM" = "true" ] && exit 0

EDITS=$(jq -r '.edits_since_checkpoint // 0' "$STATE_FILE" 2>/dev/null)
TRAJ_ID=$(jq -r '.trajectory_id // empty' "$STATE_FILE" 2>/dev/null)

# RLVR: Increment edit counter and trajectory steps
jq '.reward_signals.edit_count += 1 | .trajectory_steps += 1' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

# Check if checkpoint required (3+ edits)
if [ "$EDITS" -ge 3 ]; then
    # RLVR: Track checkpoint compliance penalty
    jq '.reward_signals.checkpoint_compliance = ((.reward_signals.checkpoint_compliance // 1.0) * 0.9)' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  ⚠️  CHECKPOINT REQUIRED: $EDITS edits since last checkpoint  ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "Update WORKING_MEMORY now before continuing." >&2

    if [ -n "$TRAJ_ID" ]; then
        echo "RLVR: Recording forced_checkpoint step (quality=0.8)" >&2
    fi

    exit 2
fi

# Log edit for RLVR
if [ -n "$TRAJ_ID" ] && [ -n "$FILE_PATH" ]; then
    BASENAME=$(basename "$FILE_PATH" 2>/dev/null || echo "$FILE_PATH")
    echo "Edit: $BASENAME (${EDITS}/3 until checkpoint)" >&2
fi

exit 0
