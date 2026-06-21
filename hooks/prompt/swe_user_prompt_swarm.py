#!/usr/bin/env python3
"""UserPromptSubmit hook - Detect swarm keywords."""

import os
import sys
import json
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "UserPromptSubmit")

# Explicit swarm terminology
SWARM_KEYWORDS = [r'\bswarm\b', r'\bmulti-agent\b', r'\bparallel\s+agents?\b', r'\bhive\b', r'\borchestrat']

# Task patterns that benefit from parallelization (folder/multi-file analysis)
PARALLEL_TASK_PATTERNS = [
    r'\breview\s+(this\s+|the\s+|a\s+)?(folder|directory|module|codebase)\b',
    r'\banalyze\s+(all|these|multiple|the|this)\s+(files?|folder|directory)\b',
    r'\bcheck\s+(all|every|each)\s+(files?|modules?)\b',
    r'\b(review|analyze|check|read)\s+\d+\+?\s+files?\b',  # "review 10 files"
    r'\blarge\s+files?\b',
    r'\bentire\s+(module|folder|directory|codebase)\b',
    r'\bmulti(ple)?-?file\b',
    r'\bacross\s+(all|multiple)\s+(files?|modules?)\b',
    r'\ball\s+(the\s+)?(files?|templates?|classes?)\s+in\b',  # "all the files in"
    r'\b(scan|audit|inspect)\s+(the\s+)?(folder|directory|codebase)\b',
]

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        prompt = get_input_field(input_data, 'prompt', default='')
        if not prompt:
            output_empty()
            return

        # Check explicit swarm keywords
        for pattern in SWARM_KEYWORDS:
            if re.search(pattern, prompt, re.IGNORECASE):
                output = HookOutput(event_name="UserPromptSubmit")
                output.add_message("🐝 SWARM HINT: This task involves swarm orchestration. Complete WF_INIT → WF_CLASSIFY first. In WF_CLASSIFY, you MUST read FEATURE_SWARM which loads WF_SWARM_ORCHESTRATE, REF_SWARM_PATTERNS, CLAUDE_FLOW, and REF_AGENTS.")
                output.output_and_exit()

        # Check parallel task patterns
        for pattern in PARALLEL_TASK_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                output = HookOutput(event_name="UserPromptSubmit")
                output.add_message("🐝 PARALLEL HINT: This task may benefit from swarm orchestration. Complete WF_INIT → WF_CLASSIFY first. In WF_CLASSIFY, consider reading FEATURE_SWARM for multi-agent coordination.")
                output.output_and_exit()

        output_empty()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": f"Prompt error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
