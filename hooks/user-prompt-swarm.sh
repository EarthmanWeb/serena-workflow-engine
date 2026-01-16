#!/bin/bash
# Hook: user-prompt-swarm.sh
# Purpose: Detect swarm/claude-flow patterns and OUTPUT WF_SWARM_ORCHESTRATE instructions

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
INSTRUCTIONS_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/instructions"
REFERENCES_DIR="$CWD/.claude/plugins/serena-workflow-engine/state-machine/references"

# Check for agent patterns in transcript
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')

if [ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ]; then
    # Check for claude-flow specific patterns
    if grep -qiE "(claude-flow|mcp__claude-flow__|hive-mind|swarm_init|agent_spawn|hooks_pre-task|hooks_post-task|CLAUDE-FLOW AGENT)" "$TRANSCRIPT" 2>/dev/null; then
        if [ -f "$STATE_FILE" ]; then
            jq '.is_claude_flow_agent = true | .is_swarm_agent = true | .current_state = "WF_SWARM_ORCHESTRATE"' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi

        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  🐝 CLAUDE-FLOW AGENT MODE DETECTED                          ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2

        # OUTPUT WF_SWARM_ORCHESTRATE INSTRUCTIONS
        SWARM_FILE="$INSTRUCTIONS_DIR/WF_SWARM_ORCHESTRATE.md"
        if [ -f "$SWARM_FILE" ]; then
            echo "" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "INSTRUCTIONS (WF_SWARM_ORCHESTRATE):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$SWARM_FILE" >&2
            echo "════════════════════════════════════════════════════════════" >&2
        fi

        # OUTPUT REF_SWARM_PATTERNS reference
        REF_SWARM="$REFERENCES_DIR/REF_SWARM_PATTERNS.md"
        if [ -f "$REF_SWARM" ]; then
            echo "" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "REFERENCE: SWARM PATTERNS (from REF_SWARM_PATTERNS.md):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$REF_SWARM" >&2
            echo "════════════════════════════════════════════════════════════" >&2
        fi

        exit 1
    fi

    # Look for generic swarm agent patterns (ruv-swarm, flow-nexus, etc.)
    if grep -qiE "(You are .*(researcher|coder|analyst|optimizer|coordinator) agent)|(Task assignment:)|(SWARM AGENT MODE)|(ruv-swarm|flow-nexus)" "$TRANSCRIPT" 2>/dev/null; then
        if [ -f "$STATE_FILE" ]; then
            jq '.is_swarm_agent = true | .current_state = "WF_SWARM_ORCHESTRATE"' "$STATE_FILE" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi

        echo "" >&2
        echo "╔══════════════════════════════════════════════════════════════╗" >&2
        echo "║  🐝 SWARM AGENT MODE DETECTED                                ║" >&2
        echo "╚══════════════════════════════════════════════════════════════╝" >&2

        # OUTPUT WF_SWARM_ORCHESTRATE INSTRUCTIONS
        SWARM_FILE="$INSTRUCTIONS_DIR/WF_SWARM_ORCHESTRATE.md"
        if [ -f "$SWARM_FILE" ]; then
            echo "" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "INSTRUCTIONS (WF_SWARM_ORCHESTRATE):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$SWARM_FILE" >&2
            echo "════════════════════════════════════════════════════════════" >&2
        fi

        # OUTPUT REF_SWARM_PATTERNS reference
        REF_SWARM="$REFERENCES_DIR/REF_SWARM_PATTERNS.md"
        if [ -f "$REF_SWARM" ]; then
            echo "" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            echo "REFERENCE: SWARM PATTERNS (from REF_SWARM_PATTERNS.md):" >&2
            echo "════════════════════════════════════════════════════════════" >&2
            cat "$REF_SWARM" >&2
            echo "════════════════════════════════════════════════════════════" >&2
        fi

        exit 1
    fi
fi

exit 0
