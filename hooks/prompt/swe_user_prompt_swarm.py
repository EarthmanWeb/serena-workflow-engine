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
        
        # Check explicit swarm keywords first
        for pattern in SWARM_KEYWORDS:
            if re.search(pattern, prompt, re.IGNORECASE):
                output = HookOutput(event_name="UserPromptSubmit")
                output.add_message("🐝 SWARM KEYWORDS DETECTED - You MUST use ruv-swarm or hive-mind swarm orchestration. Read WF_SWARM_ORCHESTRATE before continuing")
                output.output_and_exit()
        
        # Check parallel task patterns (folder/multi-file analysis)
        for pattern in PARALLEL_TASK_PATTERNS:
            if re.search(pattern, prompt, re.IGNORECASE):
                output = HookOutput(event_name="UserPromptSubmit")
                output.add_message("🐝 PARALLEL TASK PATTERN DETECTED - You MUST use ruv-swarm or hive-mind swarm orchestration for multi-file/folder analysis. Read WF_SWARM_ORCHESTRATE before continuing")
                output.output_and_exit()
        
        output_empty()
    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": f"Prompt error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)

if __name__ == '__main__':
    main()
