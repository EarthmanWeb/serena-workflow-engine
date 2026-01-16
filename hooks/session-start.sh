#!/bin/bash
# Hook: session-start.sh
# Purpose: Initialize workflow and OUTPUT instructions directly from WF_START.md

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
SETUP_FILE="$CWD/.claude/setup-complete.json"
INSTRUCTIONS_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/instructions"
REFERENCES_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/references"
WF_START_FILE="$INSTRUCTIONS_DIR/WF_START.md"

# Check if setup already complete
if [ -f "$SETUP_FILE" ]; then
    SETUP_DONE=$(jq -r '.complete // false' "$SETUP_FILE" 2>/dev/null)
    if [ "$SETUP_DONE" != "true" ]; then
        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  INITIAL SETUP REQUIRED                                      ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2
        echo "" >&2
        echo "Run /swe-init to complete first-time setup." >&2
        echo "" >&2
        exit 1
    fi
else
    # No setup file = first time
    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  SERENA WORKFLOW ENGINE - First Time Setup                   ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "Run /swe-init to initialize the plugin." >&2
    echo "" >&2
    exit 1
fi

# Check for existing state file (resuming session)
if [ -f "$STATE_FILE" ]; then
    LAST_STATE=$(jq -r '.current_state' "$STATE_FILE" 2>/dev/null)
    WM_FILE=$(jq -r '.working_memory_file // empty' "$STATE_FILE" 2>/dev/null)

    echo "" >&2
    echo "╔══════════════════════════════════════════════════════════════╗" >&2
    echo "║  RESUMING SESSION                                            ║" >&2
    echo "╚══════════════════════════════════════════════════════════════╝" >&2
    echo "" >&2
    echo "Last state: $LAST_STATE" >&2
    [ -n "$WM_FILE" ] && echo "Working Memory: $WM_FILE" >&2
    echo "" >&2
    echo "To continue, read your WORKING_MEMORY file:" >&2
    echo "  mcp__serena__read_memory(\"$WM_FILE\")" >&2
    echo "" >&2
    exit 1
fi

# ═══════════════════════════════════════════════════════════════
# NEW SESSION - Initialize state and output WF_START instructions
# ═══════════════════════════════════════════════════════════════

# Create .claude directory if needed
mkdir -p "$CWD/.claude"

# Initialize RLVR trajectory
TRAJECTORY_ID="traj_$(date +%s)_$$"

# Create initial workflow state
cat > "$STATE_FILE" << EOF
{
  "session_id": "$(date +%Y%m%d_%H%M%S)",
  "current_state": "WF_START",
  "previous_state": null,
  "edits_since_checkpoint": 0,
  "is_swarm_agent": false,
  "plan_mode": false,
  "plan_mode_entries": 0,
  "plan_mode_reason": null,
  "working_memory_file": null,
  "trajectory_id": "$TRAJECTORY_ID",
  "trajectory_steps": 0,
  "learning_complete": false,
  "computed_reward": null,
  "reward_signals": {
    "skill_returns": [],
    "state_transitions": 0,
    "clarify_count": 0,
    "edit_count": 0,
    "checkpoint_compliance": 1.0,
    "test_pass_rate": null,
    "arch_review_pass": null,
    "verify_success": null
  }
}
EOF

echo "" >&2
echo "╔══════════════════════════════════════════════════════════════╗" >&2
echo "║  🚀 SERENA WORKFLOW ENGINE - Session Started                 ║" >&2
echo "╚══════════════════════════════════════════════════════════════╝" >&2
echo "" >&2
echo "RLVR Trajectory: $TRAJECTORY_ID" >&2
echo "" >&2

# ═══════════════════════════════════════════════════════════════
# OUTPUT WF_START INSTRUCTIONS DIRECTLY FROM FILE
# ═══════════════════════════════════════════════════════════════
if [ -f "$WF_START_FILE" ]; then
    echo "════════════════════════════════════════════════════════════" >&2
    echo "WORKFLOW INSTRUCTIONS (from WF_START.md):" >&2
    echo "════════════════════════════════════════════════════════════" >&2
    echo "" >&2
    cat "$WF_START_FILE" >&2
    echo "" >&2
    echo "════════════════════════════════════════════════════════════" >&2
else
    echo "⚠️  WF_START.md not found at: $WF_START_FILE" >&2
    echo "Fallback: Read WF_START memory manually." >&2
fi

# Output REF_WORKING_MEMORY - required for WORKING_MEMORY format
REF_WM_FILE="$REFERENCES_DIR/REF_WORKING_MEMORY.md"
if [ -f "$REF_WM_FILE" ]; then
    echo "" >&2
    echo "════════════════════════════════════════════════════════════" >&2
    echo "REFERENCE: WORKING_MEMORY FORMAT (from REF_WORKING_MEMORY.md):" >&2
    echo "════════════════════════════════════════════════════════════" >&2
    echo "" >&2
    cat "$REF_WM_FILE" >&2
    echo "" >&2
    echo "════════════════════════════════════════════════════════════" >&2
fi

echo "" >&2
exit 1
