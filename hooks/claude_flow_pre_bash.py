#!/usr/bin/env python3
"""PreToolUse hook for Bash - Claude-Flow command risk assessment."""

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
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# High-risk command patterns
HIGH_RISK_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'rm\s+-rf\s+\*',
    r'dd\s+if=',
    r'mkfs\.',
    r'>\s*/dev/sd',
    r'chmod\s+-R\s+777\s+/',
    r'chown\s+-R.*/',
]

# Test syntax patterns - block incorrect test invocation
# These patterns indicate bypassing the proper test runner script
TEST_SYNTAX_BLOCK_PATTERNS = [
    r'TEST_ENV=\w+\s+npx\s+playwright\s+test',  # Direct npx playwright test with TEST_ENV
    r'cd\s+.*private/tests\s*&&\s*TEST_ENV=',   # cd to tests dir then TEST_ENV
]

# Warn patterns (not blocked)
WARN_PATTERNS = [
    r'git\s+push\s+.*--force',
    r'git\s+reset\s+--hard',
    r'npm\s+publish',
    r'docker\s+rm',
]


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        command = get_input_field(input_data, 'tool_input', 'command', default='')

        if not command:
            output_empty()

        # Check high-risk patterns
        for pattern in HIGH_RISK_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                output_block(
                    f"🚨 HIGH-RISK COMMAND BLOCKED\n\n"
                    f"Command: {command}\n"
                    f"Pattern matched: {pattern}\n\n"
                    f"This command could cause system damage."
                )

        # Check test syntax patterns - block incorrect test invocation
        for pattern in TEST_SYNTAX_BLOCK_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                output_block(
                    f"🛑 INCORRECT TEST SYNTAX BLOCKED\n\n"
                    f"Command: {command}\n"
                    f"Pattern matched: {pattern}\n\n"
                    f"You are using the wrong syntax to run tests.\n\n"
                    f"REQUIRED: Read FEATURE_TESTS before proceeding:\n"
                    f"  mcp__serena__read_memory(\"FEATURE_TESTS\")\n\n"
                    f"Use the proper test runner script, not direct npx invocation."
                )

        # Check warn patterns
        for pattern in WARN_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                output = HookOutput(event_name="PreToolUse")
                output.add_message(f"""
⚠️  CAUTION: Potentially destructive command

Command: {command}
Pattern: {pattern}

Proceeding - but verify this is intentional.
""")
                output.output_and_exit()

        output_empty()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-bash error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
