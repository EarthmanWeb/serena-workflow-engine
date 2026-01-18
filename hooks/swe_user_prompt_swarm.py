#!/usr/bin/env python3
"""UserPromptSubmit hook - Detect swarm keywords."""

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
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

SWARM_KEYWORDS = [r'\bswarm\b', r'\bmulti-agent\b', r'\bparallel\s+agents?\b', r'\bhive\b', r'\borchestrat']

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        prompt = get_input_field(input_data, 'prompt', default='')
        if not prompt:
            output_empty()
        for pattern in SWARM_KEYWORDS:
            if re.search(pattern, prompt, re.IGNORECASE):
                output = HookOutput(event_name="UserPromptSubmit")
                output.add_message("🐝 SWARM KEYWORDS DETECTED - Consider reading WF_SWARM_ORCHESTRATE")
                output.output_and_exit()
        output_empty()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": f"Prompt error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
