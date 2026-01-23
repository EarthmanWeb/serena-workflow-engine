#!/usr/bin/env python3
"""PostToolUse hook for Serena replace_content - Edit tool fallback on failure.

Detects when mcp__serena__replace_content fails and suggests using the standard
Edit tool for that specific instance. This handles cases where whitespace or
formatting differences cause Serena's literal/regex matching to fail.

IMPORTANT: This hook provides a ONE-TIME suggestion for the SPECIFIC FAILED edit.
It does not change default tool behavior - it only activates on failure.
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
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)

# Error patterns that indicate replace_content failed
FAILURE_PATTERNS = [
    r"No matches of search expression found",
    r"Error executing tool.*ValueError",
    r"Multiple occurrences found.*allow_multiple_occurrences",
    r"Error: Pattern not found",
]


def detect_failure(tool_result: str) -> bool:
    """Check if tool_result indicates a replace_content failure."""
    if not tool_result:
        return False
    
    for pattern in FAILURE_PATTERNS:
        if re.search(pattern, tool_result, re.IGNORECASE):
            return True
    return False


def extract_file_path(tool_input: dict) -> str:
    """Extract the file path from tool input."""
    return tool_input.get('relative_path', '') or tool_input.get('file_path', '')


def generate_fallback_suggestion(tool_input: dict, file_path: str) -> str:
    """Generate a suggestion to use the Edit tool instead."""
    needle = tool_input.get('needle', '')
    repl = tool_input.get('repl', '')
    mode = tool_input.get('mode', 'literal')
    
    # Truncate long strings for display
    needle_preview = needle[:100] + '...' if len(needle) > 100 else needle
    repl_preview = repl[:100] + '...' if len(repl) > 100 else repl
    
    suggestion = f"""🔄 **SERENA REPLACE FAILED** - Falling back to Edit tool

**File:** `{file_path}`
**Mode:** {mode}
**Needle preview:** `{needle_preview}`

**RECOMMENDED ACTION:**
Use the standard `Edit` tool instead for this specific edit:

```
Edit(
  file_path="{file_path}",
  old_string="<exact content from file>",
  new_string="<your replacement>"
)
```

**WHY THIS FAILED:**
- Serena's replace_content uses exact string matching
- Whitespace, indentation, or invisible characters may differ
- The Read tool output may not match the actual file bytes exactly

**TIPS FOR SUCCESS:**
1. Use `Read` tool to get the EXACT content from the file
2. Copy the old_string directly from Read output (including whitespace)
3. If still failing, try reading smaller line ranges to isolate the content
"""
    return suggestion


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        
        # Get tool information
        tool_name = get_input_field(input_data, 'tool_name', default='')
        tool_input = input_data.get('tool_input', {})
        tool_result = get_input_field(input_data, 'tool_result', default='')
        
        # Convert tool_result to string if it's a dict
        if isinstance(tool_result, dict):
            tool_result = tool_result.get('result', '') or json.dumps(tool_result)
        
        # Only process Serena replace operations
        serena_replace_tools = [
            'mcp__serena__replace_content',
            'mcp__plugin_serena-workflow-engine_serena__replace_content',
        ]
        
        if tool_name not in serena_replace_tools:
            output_empty()
            return
        
        # Check if the operation failed
        if not detect_failure(str(tool_result)):
            output_empty()
            return
        
        # Generate fallback suggestion
        file_path = extract_file_path(tool_input)
        suggestion = generate_fallback_suggestion(tool_input, file_path)
        
        output = HookOutput(event_name="PostToolUse")
        output.add_message(suggestion)
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Serena fallback hook error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
