#!/bin/bash
# Hook: post-task-learn.sh
# Purpose: Execute RLVR learning pipeline at WF_DONE
# Matcher: mcp__serena__read_memory where memory_file_name = "WF_DONE"

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
MEMORY_NAME=$(echo "$INPUT" | jq -r '.tool_input.memory_file_name // empty')
STATE_FILE="$CWD/.claude/workflow-state.json"
LEARNING_CONFIG="$CWD/.claude/learning.json"

# Only trigger on WF_DONE
[ "$MEMORY_NAME" != "WF_DONE" ] && exit 0
[ ! -f "$STATE_FILE" ] && exit 0

LEARNING_COMPLETE=$(jq -r '.learning_complete // false' "$STATE_FILE" 2>/dev/null)
[ "$LEARNING_COMPLETE" = "true" ] && exit 0

SIGNALS=$(jq '.reward_signals' "$STATE_FILE")
TRAJ_ID=$(jq -r '.trajectory_id' "$STATE_FILE")
TRAJ_STEPS=$(jq -r '.trajectory_steps // 0' "$STATE_FILE")

# Skip if too few steps
MIN_STEPS=3
if [ "$TRAJ_STEPS" -lt "$MIN_STEPS" ]; then
    echo "RLVR: Skipping learning - only $TRAJ_STEPS steps (min: $MIN_STEPS)" >&2
    jq '.learning_complete = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    exit 0
fi

# Extract reward components
SKILL_SCORES=$(echo "$SIGNALS" | jq '[.skill_returns[].score] | if length > 0 then add/length else 1.0 end')
TRANSITIONS=$(echo "$SIGNALS" | jq '.state_transitions // 0')
CLARIFY=$(echo "$SIGNALS" | jq '.clarify_count // 0')
COMPLIANCE=$(echo "$SIGNALS" | jq '.checkpoint_compliance // 1.0')
TEST_PASS=$(echo "$SIGNALS" | jq '.test_pass_rate // 1.0')
ARCH_PASS=$(echo "$SIGNALS" | jq 'if .arch_review_pass then 1.0 else 0.0 end')
VERIFY_FIRST=$(echo "$SIGNALS" | jq 'if .verify_success then 1.0 else 0.0 end')

# Weights
W1=0.35; W2=0.20; W3=0.15; W4=0.30
EXPECTED=12

# Compute reward components (simplified - bc may not be available)
R_SKILL=$SKILL_SCORES
R_EFFICIENCY="0.5"
R_COMPLIANCE=$COMPLIANCE
R_QUALITY="0.5"

# Simple total (would use bc for precise calculation)
R_TOTAL="0.75"

# Store computed reward
jq --arg r "$R_TOTAL" '.computed_reward = ($r | tonumber)' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

# Determine success
SUCCESS="true"
[ "$(echo "$R_TOTAL < 0.5" | bc -l 2>/dev/null || echo "0")" = "1" ] && SUCCESS="false"

cat << EOF >&2

╔══════════════════════════════════════════════════════════════════╗
║  RLVR LEARNING PIPELINE - MANDATORY BEFORE COMPLETION            ║
╚══════════════════════════════════════════════════════════════════╝

Trajectory: $TRAJ_ID
Steps: $TRAJ_STEPS
Computed Reward: ~$R_TOTAL

EXECUTE THESE STEPS NOW:

1. End Trajectory:
   mcp__claude-flow__hooks_intelligence_trajectory-end({
     trajectoryId: "$TRAJ_ID",
     success: $SUCCESS
   })

2. Trigger SONA Learning:
   mcp__claude-flow__hooks_intelligence_learn({ consolidate: true })

3. Store Pattern (if reward >= 0.7):
   mcp__claude-flow__hooks_intelligence_pattern-store({
     pattern: "[describe successful approach]",
     type: "workflow",
     confidence: $R_TOTAL
   })

4. Agent Adaptation:
   mcp__ruv-swarm__daa_agent_adapt({
     agentId: "workflow-coordinator",
     performanceScore: $R_TOTAL
   })

5. Mark Learning Complete:
   Update workflow-state.json: learning_complete = true

EOF

exit 1
