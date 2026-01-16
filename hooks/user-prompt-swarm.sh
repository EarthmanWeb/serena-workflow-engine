#!/bin/bash
# Hook: user-prompt-swarm.sh
# Purpose: Detect swarm agent patterns and bypass workflow enforcement

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"

# Check for swarm agent patterns in transcript
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    # Look for swarm agent assignment patterns
    if grep -qiE "(You are .*(researcher|coder|analyst|optimizer|coordinator) agent)|(Task assignment:)|(SWARM AGENT MODE)" "$TRANSCRIPT" 2>/dev/null; then
        if [ -f "$STATE_FILE" ]; then
            jq '.is_swarm_agent = true' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi
        echo "SWARM AGENT MODE - workflow enforcement bypassed" >&2
        exit 1
    fi
fi

exit 0
