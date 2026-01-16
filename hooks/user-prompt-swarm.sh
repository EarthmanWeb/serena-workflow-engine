#!/bin/bash
# Hook: user-prompt-swarm.sh
# Purpose: Detect swarm/claude-flow agent patterns and configure mode accordingly

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"

# Check for agent patterns in transcript
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    # Check for claude-flow specific patterns
    # These indicate orchestration via claude-flow MCP tools or hive-mind
    if grep -qiE "(claude-flow|mcp__claude-flow__|hive-mind|swarm_init|agent_spawn|hooks_pre-task|hooks_post-task|CLAUDE-FLOW AGENT)" "$TRANSCRIPT" 2>/dev/null; then
        if [ -f "$STATE_FILE" ]; then
            jq '.is_claude_flow_agent = true | .is_swarm_agent = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi
        echo "CLAUDE-FLOW AGENT MODE - hooks enabled, workflow enforcement bypassed" >&2
        exit 1
    fi

    # Look for generic swarm agent assignment patterns (ruv-swarm, flow-nexus, etc.)
    if grep -qiE "(You are .*(researcher|coder|analyst|optimizer|coordinator) agent)|(Task assignment:)|(SWARM AGENT MODE)|(ruv-swarm|flow-nexus)" "$TRANSCRIPT" 2>/dev/null; then
        if [ -f "$STATE_FILE" ]; then
            jq '.is_swarm_agent = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi
        echo "SWARM AGENT MODE - workflow enforcement bypassed" >&2
        exit 1
    fi
fi

exit 0
