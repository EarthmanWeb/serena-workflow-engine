#!/usr/bin/env python3
"""PostToolUse hook for mcp__ruv-swarm__swarm_init - Enforce REF_SWARM_PATTERNS read.

After initializing a ruv-swarm, Claude MUST read REF_SWARM_PATTERNS to follow
proper swarm coordination patterns (DAA init, agent spawning, orchestration).
"""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        # Check if swarm_init succeeded
        tool_result = input_data.get('tool_result', {})
        if isinstance(tool_result, dict) and tool_result.get('error'):
            # Swarm init failed, don't add instruction
            output_empty()
            return

        # Output instruction to read swarm patterns
        context = """<swarm-init-complete>
<blocking-instruction priority="HIGH">
RUV-SWARM INITIALIZED - FOLLOW PROPER PATTERN

Your NEXT ACTION must be to read the swarm coordination reference:
→ mcp__plugin_swe_serena__read_memory("REF_SWARM_PATTERNS")

This contains MANDATORY steps for proper swarm coordination:
1. daa_init (enable learning/coordination)
2. daa_agent_create (spawn agents with cognitive patterns)
3. task_orchestrate (coordinate work)

DO NOT skip this step. DO NOT guess the pattern.
Read REF_SWARM_PATTERNS NOW.
</blocking-instruction>
</swarm-init-complete>"""

        output = HookOutput(event_name="PostToolUse")
        output.add_context(context)
        output.print()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Ruv-swarm init hook error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
