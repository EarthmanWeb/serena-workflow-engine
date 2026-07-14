#!/usr/bin/env python3
"""PreToolUse hook for Bash - test gate + project Bash policy.

1. Project Bash policy: if <project>/.serena/bash-policy.json exists, each
   rule is {"pattern": <regex>, "message": <why + what to use instead>}.
   A command matching any rule is denied with the rule's message. This is the
   single enforcement point for "don't shell around sanctioned tools" rules
   (e.g. raw `docker exec ... wp` when a wp_cli MCP server is configured, or
   git commands in projects where the user handles version control). No file
   → no policy checks (fully generic/portable).

2. Test gate: detects Playwright test commands and blocks if FEATURE_TESTS
   hasn't been loaded. Uses session-scoped sentinel file (created by
   swe_post_read_state.py). Same pattern as swe_pre_swarm_feature_gate.py.
"""

import os
import sys
import json
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_dir
    from swe_hooks.core.config import get_project_root
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# Only gate on actual Playwright test execution via npx
TEST_COMMAND_PATTERNS = [
    r'\bnpx\s+playwright\s+test\b',
]


def load_bash_policy():
    """Load optional project Bash deny-policy.

    Format of <project>/.serena/bash-policy.json:
        [{"pattern": "<python regex>", "message": "<why + sanctioned alternative>"}]

    Missing/invalid file or malformed rules → empty policy (no-op).
    """
    try:
        path = os.path.join(get_project_root(), '.serena', 'bash-policy.json')
        with open(path, 'r', encoding='utf-8') as f:
            rules = json.load(f)
        if not isinstance(rules, list):
            return []
        return [r for r in rules
                if isinstance(r, dict) and r.get('pattern') and r.get('message')]
    except (IOError, json.JSONDecodeError, ValueError):
        return []


def check_bash_policy(command: str):
    """Return the first policy rule the command violates, else None."""
    for rule in load_bash_policy():
        try:
            if re.search(rule['pattern'], command, re.IGNORECASE | re.DOTALL):
                return rule
        except re.error:
            continue  # skip malformed patterns rather than blocking everything
    return None


def get_test_sentinel_path(session_id: str) -> str:
    """Get sentinel file path for FEATURE_TESTS read confirmation."""
    return os.path.join(get_stream_dir(), f'.test_feature_{session_id}')


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

        if not command:
            output_empty()
            return

        # Project Bash policy (deny-list) — checked before the test gate.
        violated = check_bash_policy(command)
        if violated:
            output_block(
                f"⛔ BASH POLICY VIOLATION\n\n"
                f"{violated['message']}\n\n"
                f"(Matched rule: {violated['pattern']} — "
                f"policy source: .serena/bash-policy.json)"
            )
            return

        if not is_test_command(command):
            output_empty()
            return

        # Extract session ID
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Check sentinel file
        if session_id:
            sentinel = get_test_sentinel_path(session_id)
            if os.path.exists(sentinel):
                output_empty()
                return

        # BLOCK - FEATURE_TESTS not read
        output_block(
            f"""🧪 TEST COMMAND BLOCKED - FEATURE_TESTS not read for session {session_id or 'unknown'}

You MUST read FEATURE_TESTS before running test commands.

MANDATORY ACTION:
  mcp__plugin_swe_serena__read_memory(memory_name="feature/FEATURE_TESTS")

Then retry the test command."""
        )

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Test gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
