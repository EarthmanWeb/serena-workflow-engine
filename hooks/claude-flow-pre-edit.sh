#!/bin/bash
# Hook: claude-flow-pre-edit.sh
# Purpose: Conditionally invoke claude-flow pre-edit hook when operating as claude-flow agent
# NOTE: This COMPLEMENTS existing pre-edit-validate.sh, does not replace it

# REQUIRED: Parse stdin JSON (env vars are BROKEN - GitHub #9567)
INPUT=$(cat)
CWD=$(echo "$INPUT" | jq -r '.cwd')
STATE_FILE="$CWD/.claude/workflow-state.json"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // empty')

# Exit early if no state file or not claude-flow mode
[ ! -f "$STATE_FILE" ] && exit 0

IS_CLAUDE_FLOW=$(jq -r '.is_claude_flow_agent // false' "$STATE_FILE" 2>/dev/null)

# Only run claude-flow hooks when in claude-flow agent mode
if [ "$IS_CLAUDE_FLOW" = "true" ] && [ -n "$FILE_PATH" ]; then
    # Check if npx is available
    if command -v npx &> /dev/null; then
        # Run claude-flow pre-edit hook (non-blocking, capture errors)
        npx claude-flow@alpha hooks pre-edit \
            --file "$FILE_PATH" \
            --auto-assign-agents true \
            --load-context true 2>&1 || true

        CF_EXIT=$?
        if [ $CF_EXIT -ne 0 ]; then
            echo "claude-flow pre-edit: warning (exit $CF_EXIT)" >&2
        fi
    else
        echo "claude-flow: npx not available, skipping pre-edit hook" >&2
    fi
fi

# Always exit 0 - this hook complements, doesn't block
# The blocking logic is in pre-edit-validate.sh
exit 0
