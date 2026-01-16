#!/bin/bash
# Hook: post-edit-checkpoint.sh
# Purpose: Track edits, enforce checkpoint, and OUTPUT WF_CHECKPOINT instructions

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
INSTRUCTIONS_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/instructions"
REFERENCES_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/references"
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
    echo "║  💾 CHECKPOINT REQUIRED: $EDITS edits since last checkpoint  ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2

    # OUTPUT WF_CHECKPOINT INSTRUCTIONS
    CHECKPOINT_FILE="$INSTRUCTIONS_DIR/WF_CHECKPOINT.md"
    if [ -f "$CHECKPOINT_FILE" ]; then
        echo "" >&2
        echo "════════════════════════════════════════════════════════════" >&2
        echo "INSTRUCTIONS (WF_CHECKPOINT):" >&2
        echo "════════════════════════════════════════════════════════════" >&2
        cat "$CHECKPOINT_FILE" >&2
        echo "════════════════════════════════════════════════════════════" >&2
    else
        echo "" >&2
        echo "Update WORKING_MEMORY now before continuing." >&2
        echo "  mcp__serena__edit_memory(\"WORKING_MEMORY_...\", ...)" >&2
    fi

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

    if [ -n "$TRAJ_ID" ]; then
        echo "" >&2
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
