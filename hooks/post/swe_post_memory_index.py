#!/usr/bin/env python3
"""PostToolUse hook for write_memory - Enforce a TERSE MEMORY.md index.

MEMORY.md is an INDEX, not a content store. It is loaded into context every
session, so it must stay small: one line per memory, each a short pointer of the
form `- [Title](path) — short hook`, with the actual detail living in the linked
topic file. This hook fires after every write_memory and:

  1. Reminds the agent to add a one-line index entry for an indexable memory
     that is missing from MEMORY.md.
  2. Warns when MEMORY.md has drifted past its size budget (lines / bytes), so
     bloat gets trimmed instead of silently accumulating.
  3. Warns when non-indexed categories have leaked INTO the index — reports,
     specs, research and project memories are NOT indexed in MEMORY.md (they are
     discovered via list_memories(topic="report"|"spec"|"research"|"project")).
     If found in MEMORY.md, they should be removed.

Never-indexed prefixes (no "add an entry" reminder): WM_* (session files),
wf/* (workflow states), claude/* (obligations), and the four topic categories
that are browsed rather than indexed — spec/*|SPEC_* (specifications),
report/*|REPORT_* (reports), research/*|RESEARCH_* (research notes), and
project/*|PROJECT_* (project notes).
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

# Memory prefixes that are never indexed in MEMORY.md. Each browsable topic is
# listed under BOTH addressing styles (topic path "spec/SPEC_FOO" and bare
# basename "SPEC_FOO") because write_memory accepts either.
#
#   WM_/wf/claude  — session, workflow and obligation files (not project docs)
#   spec/SPEC_      — specifications  → list_memories(topic="spec")
#   report/REPORT_  — reports         → list_memories(topic="report")
#   research/RESEARCH_ — research     → list_memories(topic="research")
#   project/PROJECT_ — project notes  → list_memories(topic="project")
SKIP_PREFIXES = (
    "WM_", "wf/", "claude/",
    "spec/", "SPEC_",
    "report/", "REPORT_",
    "research/", "RESEARCH_",
    "project/", "PROJECT_",
)

# Categories that must NOT appear as index entries in MEMORY.md. If one is found,
# the hook flags it for removal. (Same set as the browsable topics above.)
NON_INDEXED_CATEGORIES = ("spec", "report", "research", "project")

# MEMORY.md size budget. It is loaded into context every session, so it must stay
# a lean index. Exceeding either ceiling triggers a trim reminder.
MEMORY_MD_MAX_LINES = 200
MEMORY_MD_MAX_BYTES = 24000

# A single index entry should be a short pointer, not a pasted-in summary.
INDEX_ENTRY_MAX_CHARS = 200


def check_memory_md_health(memory_md_content):
    """Return a list of warning strings if MEMORY.md has drifted from a lean index.

    Checks the size budget and scans for non-indexed categories (report/spec/
    research/project) that have leaked into the index.
    """
    warnings = []

    lines = memory_md_content.splitlines()
    n_lines = len(lines)
    n_bytes = len(memory_md_content.encode("utf-8"))
    if n_lines > MEMORY_MD_MAX_LINES or n_bytes > MEMORY_MD_MAX_BYTES:
        warnings.append(
            f"MEMORY.md is {n_lines} lines / {n_bytes // 1000}KB — over the "
            f"{MEMORY_MD_MAX_LINES}-line / {MEMORY_MD_MAX_BYTES // 1000}KB budget. "
            f"It is an INDEX loaded every session: collapse each entry to one "
            f"`- [Title](path) — short hook` line (≤{INDEX_ENTRY_MAX_CHARS} chars), "
            f"drop pasted-in detail (it lives in the linked topic file), and merge "
            f"per-memory `##` sections into a few category headers."
        )

    # Over-long index bullets (pasted-in detail instead of a pointer).
    long_bullets = [
        ln for ln in lines
        if ln.lstrip().startswith("- [") and len(ln) > INDEX_ENTRY_MAX_CHARS
    ]
    if long_bullets:
        warnings.append(
            f"{len(long_bullets)} index entr{'y' if len(long_bullets) == 1 else 'ies'} "
            f"exceed {INDEX_ENTRY_MAX_CHARS} chars — trim to a one-line pointer; "
            f"the detail belongs in the linked topic file, not the index."
        )

    # Non-indexed categories leaked into the index.
    leaked = []
    for cat in NON_INDEXED_CATEGORIES:
        # Match a markdown link into that topic dir, e.g. "](report/REPORT_X.md)".
        if f"]({cat}/" in memory_md_content:
            leaked.append(cat)
    if leaked:
        warnings.append(
            f"MEMORY.md links {', '.join(leaked)} memories — these categories are "
            f"NOT indexed here (browse them with list_memories(topic=…)). Remove "
            f"those entries from MEMORY.md."
        )

    return warnings


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

        # Find and read MEMORY.md (needed for both the index reminder and the
        # health check).
        memory_md_path = find_memory_md(cwd)
        if not memory_md_path:
            output_empty()
            return

        with open(memory_md_path, 'r', encoding='utf-8') as f:
            memory_md_content = f.read()

        messages = []

        # 1. Index reminder — only for indexable memories that are missing.
        #    Non-indexed categories (spec/report/research/project + WM/wf/claude)
        #    never get an "add an entry" nudge.
        is_indexable = not any(
            memory_name.startswith(prefix) for prefix in SKIP_PREFIXES
        )
        if is_indexable and not memory_name_in_index(memory_name, memory_md_content):
            messages.append(
                f"📋 MEMORY.md index update required: Memory \"{memory_name}\" was "
                f"created but has no entry in MEMORY.md. Add ONE terse line "
                f"(≤{INDEX_ENTRY_MAX_CHARS} chars, detail stays in the topic file):\n"
                f"  `- [Title]({memory_name}.md) — short hook`"
            )

        # 2. Health check — size budget, over-long entries, leaked categories.
        #    Runs on every write so drift is caught even when the current memory
        #    is itself non-indexable.
        messages.extend(check_memory_md_health(memory_md_content))

        if messages:
            output_message("\n".join(messages))
        else:
            output_empty()

    except Exception:
        output_empty()


if __name__ == "__main__":
    main()
