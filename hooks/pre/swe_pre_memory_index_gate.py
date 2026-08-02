#!/usr/bin/env python3
"""PreToolUse hook — HARD-DENY non-indexed category links entering MEMORY.md.

MEMORY.md is the auto-loaded session index. spec/report/research/project
memories are browsed via list_memories(topic=...) and are NEVER indexed there —
an indexed spec rides into every session's context and gets read as general
feature knowledge (the exact leak this gate closes).

swe_post_memory_index.py already states the rule but is PostToolUse-advisory:
it cannot deny, and it only fires on write_memory — index edits made via
edit_memory or raw Edit/Write slipped through. This gate runs BEFORE the write
and denies it, state-independently.

Matches: write_memory / edit_memory (Serena, both server prefixes) + Edit/Write.
Fires ONLY when the target is the MEMORY index AND the written content
introduces a link into a non-indexed category. Everything else passes silently.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# Categories that must never appear as MEMORY.md index links. Keep in sync with
# NON_INDEXED_CATEGORIES in hooks/post/swe_post_memory_index.py.
NON_INDEXED_CATEGORIES = ("spec", "report", "research", "project")

# Markdown link whose target is inside a non-indexed topic dir, e.g.
# "](spec/SPEC_X.md)" or "](.serena/memory/report/REPORT_Y.md)".
_CATEGORY_DIR_LINK = re.compile(
    r"\]\(\s*[^)]*\b(?:%s)/" % "|".join(NON_INDEXED_CATEGORIES), re.IGNORECASE
)
# Markdown link to a category file by bare basename, e.g. "](SPEC_X.md)".
_CATEGORY_FILE_LINK = re.compile(
    r"\]\(\s*[^)/]*\b(?:SPEC|REPORT|RESEARCH|PROJECT)_[^)]*\.md\s*\)"
)

# Content-bearing fields across the matched tools:
#   write_memory: content · edit_memory: repl · Edit: new_string · Write: content
CONTENT_FIELDS = ("content", "repl", "new_string")


def targets_memory_index(tool_input):
    """True when the call writes the MEMORY.md index (by memory name or path)."""
    memory_name = str(tool_input.get("memory_name", ""))
    if memory_name in ("MEMORY", "MEMORY.md"):
        return True
    file_path = str(tool_input.get("file_path", ""))
    return os.path.basename(file_path.replace("\\", "/")) == "MEMORY.md"


def written_category_links(tool_input):
    """Return the non-indexed categories the written content would link."""
    blob = " ".join(str(tool_input.get(k, "")) for k in CONTENT_FIELDS)
    found = set()
    for match in _CATEGORY_DIR_LINK.finditer(blob):
        seg = match.group(0).lower()
        for cat in NON_INDEXED_CATEGORIES:
            if cat + "/" in seg:
                found.add(cat)
    if _CATEGORY_FILE_LINK.search(blob):
        for cat in NON_INDEXED_CATEGORIES:
            if re.search(r"\]\([^)/]*\b%s_" % cat.upper(), blob):
                found.add(cat)
    return sorted(found)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_input = input_data.get("tool_input", {}) or {}

        if not targets_memory_index(tool_input):
            output_empty()
            return

        leaked = written_category_links(tool_input)
        if not leaked:
            output_empty()
            return

        output = HookOutput(event_name="PreToolUse")
        output.block(
            "🛑 BLOCKED: this write adds {cats} link(s) to MEMORY.md.\n"
            "MEMORY.md is the auto-loaded session index — spec/report/research/"
            "project memories are NEVER indexed there. They are discovered via "
            "list_memories(topic=\"spec\"|\"report\"|\"research\"|\"project\") "
            "when a task explicitly needs them.\n"
            "Remove the {cats} link(s) from your update and re-issue it; the "
            "memory itself stays where it is.".format(cats="/".join(leaked))
        )
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Memory-index gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == "__main__":
    main()
