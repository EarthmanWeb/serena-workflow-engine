#!/bin/bash
# Hook: session-start.sh
# Purpose: Initialize workflow state and RLVR trajectory at session start

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
SETUP_FILE="$CWD/.claude/setup-complete.json"
LEARNING_CONFIG="$CWD/.claude/learning.json"

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
    echo "Resuming session at $LAST_STATE." >&2
    [ -n "$WM_FILE" ] && echo "Read $WM_FILE to continue." >&2
    exit 1
fi

# Create .claude directory if needed
mkdir -p "$CWD/.claude"

# Initialize RLVR trajectory
TRAJECTORY_ID="traj_$(date +%s)_$$"

# Create initial workflow state
cat > "$STATE_FILE" << EOF
{
  "session_id": "$(date +%Y%m%d_%H%M%S)",
  "current_state": "UNINITIALIZED",
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

# Create default learning config if not exists
if [ ! -f "$LEARNING_CONFIG" ]; then
    cat > "$LEARNING_CONFIG" << 'LEOF'
{
  "learning": {
    "enabled": true,
    "mandatory": true,
    "providers": {
      "trajectory": "claude-flow",
      "patterns": "claude-flow",
      "adaptation": "ruv-swarm",
      "consensus": "hive-mind"
    },
    "rewards": {
      "weights": {
        "skill": 0.35,
        "efficiency": 0.20,
        "compliance": 0.15,
        "quality": 0.30
      }
    },
    "trajectory": {
      "minStepsToLearn": 3,
      "maxStepsBeforeConsolidate": 50
    },
    "patterns": {
      "minConfidenceToStore": 0.7
    },
    "adaptation": {
      "learningRate": 0.8,
      "patternSwitchThreshold": 0.3
    }
  }
}
LEOF
fi

echo "" >&2
echo "╔══════════════════════════════════════════════════════════════╗" >&2
echo "║  SERENA WORKFLOW ENGINE - Session Initialized                ║" >&2
echo "╚══════════════════════════════════════════════════════════════╝" >&2
echo "" >&2
echo "MANDATORY: Read WF_START before ANY response." >&2
echo "RLVR: Trajectory $TRAJECTORY_ID initialized." >&2
echo "" >&2
exit 1
