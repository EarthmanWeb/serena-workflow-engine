#!/usr/bin/env python3
"""PostToolUse hook for write_memory - Enforce MEMORY.md index update.

After a new memory is created via write_memory, checks if the memory name
appears in MEMORY.md. If not, reminds the agent to add an index entry.

Skips WM_* (session files), wf/* (workflow states), claude/* (obligations),
and spec/* | SPEC_* (specifications) since these are not indexed in MEMORY.md.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_message
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import get_project_root
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUse")

# Memory prefixes that are never indexed in MEMORY.md.
# spec/ and SPEC_ cover specification memories under both addressing styles
# (topic path "spec/SPEC_FOO" and bare basename "SPEC_FOO") — specs are tracked
# via list_memories(topic="spec"), not the MEMORY.md index.
SKIP_PREFIXES = ("WM_", "wf/", "claude/", "spec/", "SPEC_")


def find_memory_md(cwd):
    """Locate MEMORY.md in the project's .serena/memory/ directory."""
    project_root = get_project_root()
    path = os.path.join(project_root, ".serena", "memory", "MEMORY.md")
    if os.path.isfile(path):
        return path
    # Fallback: check cwd-based path
    path = os.path.join(cwd, ".serena", "memory", "MEMORY.md")
    if os.path.isfile(path):
        return path
    return None


def memory_name_in_index(memory_name, memory_md_content):
    """Check if the memory name (or its basename) appears in MEMORY.md."""
    # Extract basename: "feature/FEATURE_SWE" -> "FEATURE_SWE"
    basename = memory_name.split("/")[-1] if "/" in memory_name else memory_name
    # Check for the basename in the content (with or without .md extension)
    return basename in memory_md_content or f"{basename}.md" in memory_md_content


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        memory_name = get_input_field(input_data, 'tool_input', 'memory_name', default='')

        if not memory_name:
            output_empty()
            return

        # Skip memories that are never indexed
        if any(memory_name.startswith(prefix) for prefix in SKIP_PREFIXES):
            output_empty()
            return

        # Find and read MEMORY.md
        memory_md_path = find_memory_md(cwd)
        if not memory_md_path:
            output_empty()
            return

        with open(memory_md_path, 'r', encoding='utf-8') as f:
            memory_md_content = f.read()

        # Check if already indexed
        if memory_name_in_index(memory_name, memory_md_content):
            output_empty()
            return

        # Not found — remind agent to update MEMORY.md
        output_message(
            f"📋 MEMORY.md index update required: Memory \"{memory_name}\" was created "
            f"but has no entry in MEMORY.md. Add a one-line index entry now:\n"
            f"  `- [Title]({memory_name}.md) — short description`"
        )

    except Exception:
        output_empty()


if __name__ == "__main__":
    main()
