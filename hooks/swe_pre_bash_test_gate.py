#!/usr/bin/env python3
"""PreToolUse hook for Bash - Ensure FEATURE_TESTS is read before running tests.

Detects test commands and reminds/blocks if FEATURE_TESTS hasn't been loaded.
Uses session-scoped tracking of read memories.
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

# Test command patterns
TEST_COMMAND_PATTERNS = [
    r'\bplaywright\b',
    r'\bnpx\s+playwright\b',
    r'\bnpm\s+(run\s+)?test',
    r'\byarn\s+test',
    r'\bpnpm\s+test',
    r'\bpytest\b',
    r'\bphpunit\b',
    r'\bjest\b',
    r'\bmocha\b',
    r'\bvitest\b',
    r'\bava\b',
    r'\btap\b',
    r'\.spec\.(ts|js|tsx|jsx)',
    r'\.test\.(ts|js|tsx|jsx)',
    r'\btest:',  # npm scripts like "test:e2e"
]

# States where tests are expected (no reminder needed)
TEST_STATES = {'WF_VERIFY', 'WF_DEBUG_TDD'}


def check_feature_tests_read(wm_filepath: str) -> bool:
    """Check if FEATURE_TESTS is listed in the working memory's feature keys or memories read."""
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        # Check if FEATURE_TESTS is in feature keys
        if 'FEATURE_TESTS' in content:
            return True

        # Check if TESTS is mentioned in feature keys section
        feature_match = re.search(r'\*\*Feature Key\(s\)\*\*:\s*(.+)', content)
        if feature_match:
            features = feature_match.group(1)
            if 'TESTS' in features.upper():
                return True

        return False
    except IOError:
        return False


def is_test_command(command: str) -> bool:
    """Check if the command is a test command."""
    for pattern in TEST_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        command = get_input_field(input_data, 'tool_input', 'command', default='')
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        if not command:
            output_empty()
            return

        # Only check test commands
        if not is_test_command(command):
            output_empty()
            return

        # Extract session ID
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Get state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)
        current_state = state_mgr.get_current_state()

        # If already in test state, allow through
        if current_state in TEST_STATES:
            output_empty()
            return

        # Check if FEATURE_TESTS was read (from working memory)
        wm_filepath = find_working_memory_for_session(cwd, session_id)
        if check_feature_tests_read(wm_filepath):
            output_empty()
            return

        # FEATURE_TESTS not read - block with reminder
        output_block(
            f"""🧪 TEST COMMAND DETECTED - FEATURE_TESTS REQUIRED

Command: {command}

Before running tests, you MUST read FEATURE_TESTS to understand:
- Test structure and organization
- Required fixtures and setup
- Environment configuration
- Running test commands properly

REQUIRED ACTION:
```
mcp__serena__read_memory("FEATURE_TESTS")
```

After reading FEATURE_TESTS, update your WM with:
- **Feature Key(s)**: TESTS (or add TESTS to existing list)

Then retry the test command."""
        )

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Test gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
