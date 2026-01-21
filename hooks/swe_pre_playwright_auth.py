#!/usr/bin/env python3
"""PreToolUse hook for mcp__playwright__browser_navigate - Ensure auth memories are read.

Detects Playwright browser navigation and reminds/blocks if MCP auth memories
haven't been loaded (REF_CHROME_DEVTOOLS_MCP, SYS_WPMS_LOGIN, REF_TESTS_AUTH).
"""

import os
import sys
import json
import re

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# Auth memories that should be read before browser navigation
AUTH_MEMORIES = [
    'REF_CHROME_DEVTOOLS_MCP',
    'SYS_WPMS_LOGIN',
    'REF_TESTS_AUTH',
]

# Patterns to detect in working memory that indicate auth knowledge
AUTH_KNOWLEDGE_PATTERNS = [
    r'REF_CHROME_DEVTOOLS_MCP',
    r'SYS_WPMS_LOGIN',
    r'REF_TESTS_AUTH',
    r'user-registry',
    r'loginAs',
    r'storage-state',
]


def check_auth_memories_read(wm_filepath: str) -> bool:
    """Check if auth-related memories have been read based on working memory content."""
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        # Check for any auth memory references
        for pattern in AUTH_KNOWLEDGE_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                return True

        return False
    except IOError:
        return False


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='')
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Only check mcp__playwright__browser_navigate
        if tool_name != 'mcp__playwright__browser_navigate':
            output_empty()
            return

        # Extract session ID
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Check if auth memories were read (from working memory)
        wm_filepath = find_working_memory_for_session(cwd, session_id)
        if check_auth_memories_read(wm_filepath):
            output_empty()
            return

        # Auth memories not read - block with reminder
        output_block(
            """🔐 BROWSER NAVIGATION DETECTED - AUTH MEMORIES REQUIRED

Before navigating with mcp__playwright__browser_navigate, you MUST read:

```
mcp__serena__read_memory("REF_CHROME_DEVTOOLS_MCP")
mcp__serena__read_memory("SYS_WPMS_LOGIN")
```

These memories contain:
- Test environment URLs and HTTP basic auth
- User registry location for credentials
- Login workflow patterns
- Available test roles

⚠️ DO NOT guess URLs or credentials. Read the memories first.

After reading, update WORKING_MEMORY to note the auth context."""
        )

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Playwright auth gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
