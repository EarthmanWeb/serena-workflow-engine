#!/usr/bin/env python3
"""PreToolUse hook for Bash - Ensure FEATURE_TESTS is read before running tests.

Detects test commands and reminds/blocks if FEATURE_TESTS hasn't been loaded.
Uses session-scoped tracking of read memories with optional timestamp validation.
Outputs debug info on every test command to show WHY it passed or blocked.
"""

import os
import sys
import json
import re
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_block, output_message
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# Only gate on actual Playwright test execution via npx
TEST_COMMAND_PATTERNS = [
    r'\bnpx\s+playwright\s+test\b',
]

# States where tests are expected (no reminder needed)
TEST_STATES = {'WF_VERIFY', 'WF_DEBUG_TDD'}

# Timestamp expiry in seconds (5 minutes) - set to 0 to disable timestamp checking
TIMESTAMP_EXPIRY_SECONDS = 300


def check_feature_tests_read(wm_filepath: str) -> dict:
    """Check if FEATURE_TESTS is listed in the working memory.

    Returns dict with:
        - passed: bool - whether the check passed
        - reason: str - why it passed or failed
        - timestamp: int or None - timestamp if found
        - timestamp_valid: bool or None - if timestamp is within expiry window
    """
    result = {
        'passed': False,
        'reason': 'Unknown',
        'timestamp': None,
        'timestamp_valid': None,
        'wm_exists': False,
        'has_feature_tests': False,
        'has_tests_in_features': False,
    }

    if not wm_filepath:
        result['reason'] = 'No working memory filepath provided'
        return result

    if not os.path.exists(wm_filepath):
        result['reason'] = f'Working memory file not found: {wm_filepath}'
        return result

    result['wm_exists'] = True

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        # Check for timestamp marker: "Test Docs: Read @<timestamp>"
        timestamp_match = re.search(r'Test Docs: Read @(\d+)', content)
        if timestamp_match:
            result['timestamp'] = int(timestamp_match.group(1))
            current_time = int(time.time())
            age_seconds = current_time - result['timestamp']

            if TIMESTAMP_EXPIRY_SECONDS > 0:
                result['timestamp_valid'] = age_seconds <= TIMESTAMP_EXPIRY_SECONDS
                if result['timestamp_valid']:
                    result['passed'] = True
                    result['reason'] = f'Timestamp valid (age: {age_seconds}s, max: {TIMESTAMP_EXPIRY_SECONDS}s)'
                    return result
                else:
                    # HARD FAIL - timestamp exists but expired, must re-read FEATURE_TESTS
                    result['passed'] = False
                    result['reason'] = f'Timestamp EXPIRED - must re-read FEATURE_TESTS (age: {age_seconds}s, max: {TIMESTAMP_EXPIRY_SECONDS}s)'
                    return result

        # Only check fallbacks if NO timestamp exists at all
        # Check if FEATURE_TESTS is in content
        if 'FEATURE_TESTS' in content:
            result['has_feature_tests'] = True
            result['passed'] = True
            result['reason'] = 'FEATURE_TESTS found in working memory content'
            return result

        # Check if TESTS is mentioned in feature keys section
        feature_match = re.search(r'\*\*Feature Key\(s\)\*\*:\s*(.+)', content)
        if feature_match:
            features = feature_match.group(1)
            if 'TESTS' in features.upper():
                result['has_tests_in_features'] = True
                result['passed'] = True
                result['reason'] = f'TESTS found in Feature Keys: {features}'
                return result

        result['reason'] = 'No FEATURE_TESTS or TESTS marker found in working memory'
        return result

    except IOError as e:
        result['reason'] = f'IOError reading working memory: {e}'
        return result


def is_test_command(command: str) -> bool:
    """Check if the command is a test command."""
    for pattern in TEST_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def format_debug_info(session_id: str, current_state: str, wm_filepath: str, check_result: dict, bypass_reason: str = None) -> str:
    """Format debug information for hook output."""
    lines = [
        "🔍 TEST GATE DEBUG INFO:",
        f"  Session: {session_id}",
        f"  State: {current_state}",
        f"  WM Path: {wm_filepath or 'None'}",
        f"  WM Exists: {check_result.get('wm_exists', False)}",
    ]

    if check_result.get('timestamp'):
        lines.append(f"  Timestamp: {check_result['timestamp']} (valid: {check_result.get('timestamp_valid')})")

    lines.extend([
        f"  Has FEATURE_TESTS: {check_result.get('has_feature_tests', False)}",
        f"  Has TESTS in Features: {check_result.get('has_tests_in_features', False)}",
        f"  Check Passed: {check_result.get('passed', False)}",
        f"  Reason: {check_result.get('reason', 'Unknown')}",
    ])

    if bypass_reason:
        lines.append(f"  Bypass: {bypass_reason}")

    return "\n".join(lines)


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

        # Find working memory
        wm_filepath = find_working_memory_for_session(cwd, session_id)

        # Check if FEATURE_TESTS was read
        check_result = check_feature_tests_read(wm_filepath)

        # If already in test state, allow through with debug info
        if current_state in TEST_STATES:
            debug_info = format_debug_info(session_id, current_state, wm_filepath, check_result,
                                          bypass_reason=f"In test state: {current_state}")
            output_message(debug_info)
            return

        # If check passed, allow through with debug info
        if check_result['passed']:
            debug_info = format_debug_info(session_id, current_state, wm_filepath, check_result)
            output_message(debug_info)
            return

        # FEATURE_TESTS not read - block with reminder and debug info
        debug_info = format_debug_info(session_id, current_state, wm_filepath, check_result)

        output_block(
            f"""🧪 TEST COMMAND DETECTED - FEATURE_TESTS REQUIRED

{debug_info}

Command: {command}

Before running tests, you MUST read FEATURE_TESTS to understand:
- Test structure and organization
- Required fixtures and setup
- Environment configuration
- Running test commands properly

REQUIRED ACTION:
```
mcp__plugin_swe_serena__read_memory(memory_file_name="FEATURE_TESTS")
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
