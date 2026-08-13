#!/usr/bin/env python3
"""PreToolUse hook for Grep/Glob/search_for_pattern/Bash-inspection —
DOCS-FIRST blocking gate.

The informational docs-first hint (swe_post_search_docs_hint.py) fires only
AFTER repeated undocumented searches — the violation has already happened.
This gate inverts that: surfing the codebase is DENIED unless the agent holds
docs-consult budget — see "Clearing" below.

Covered vectors — the ways an agent reverse-engineers instead of reading docs
(a deploy task answered with `cat package.json` + `head .github/workflows/`, or
a plugin-location question answered with `ls … | find … | grep`, is the
canonical violation):
  - Grep / Glob / search_for_pattern — wide searches
  - Bash INSPECTION/recon commands (cat/head/tail/less/grep/rg/find/ls/tree/
    awk/sed and git status/diff/log/show/blame), INCLUDING inside a pipeline —
    mutation/build/test commands are NOT gated

Deliberately NOT gated: the Read tool. Opening a specific, known file (a source
file you already located, CLAUDE.md, a config) is not untargeted surfing — it
is the normal way to do the work. Only wide searches and Bash recon count
against the budget.

Clearing the gate is deliberately cheap and BUDGETED: ONE docs consult
(read_memory / list_memories / search_memories_by_name /
search_memories_by_front_matter → 'docread' event) clears the gate for the
next GATED_CALL_BUDGET gated calls. Each allowed gated call appends a 'gated'
event; when the budget is spent the gate re-fires and another docs consult
refills it. Clearance survives turn boundaries — there is no per-prompt
re-arm. There is no other escape.

Exemptions (fail-open by design):
  - Subagent transcript (<session>/subagents/agent-*.jsonl) → spawned agent;
    subagents bypass the workflow and must not be doc-gated, allow. (Their
    path contains the PARENT session UUID, so the sentinel check below would
    NOT exempt them — this check must come first.)
  - No session id / no stream → not a managed session, allow.
  - No init sentinel → unmanaged session, allow.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, is_subagent_transcript
    from swe_hooks.core.stream import (
        get_stream_path, get_sentinel_path, append_event,
        events_since_task_start, collect_values_since_task_start,
        normalize_memory_name,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


# One docs consult clears the gate for this many gated calls.
GATED_CALL_BUDGET = 5

# Bash command words that are pure inspection/recon — reading state instead of
# consulting docs. Matched ANYWHERE in the command (start, after a separator,
# OR after a pipe) so `ls … | find … | grep` — recon dressed as a pipeline — is
# caught. Patterns run without re.MULTILINE, so the alternation lists \n too.
# Mutation, build, and test commands are deliberately absent: they do work.
BASH_INSPECT_RE = re.compile(
    r'(^|[\n;&|]\s*)('
    r'(cat|head|tail|less|more|grep|rg|find|ls|tree|awk|sed)\b'
    r'|git\s+(status|diff|log|show|blame)\b'
    r')',
    re.IGNORECASE,
)


def is_gated_call(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call is a docs-first-gated code-surf.

    Grep/Glob/search_for_pattern: always gated.
    Bash: gated only when a command segment is inspection/recon (incl. inside a
    pipeline). Mutation/build/test commands pass through.
    Read: NEVER gated — opening a specific known file is not surfing.
    Anything else: not gated.
    """
    tool_input = tool_input or {}
    if tool_name in ('Grep', 'Glob') or tool_name.endswith('search_for_pattern'):
        return True
    if tool_name == 'Bash':
        return bool(BASH_INSPECT_RE.search(str(tool_input.get('command', ''))))
    return False


# docread names that refill even when repeated: credited memory searches
# (a search confirming already-read docs is the sanctioned re-consult).
ALWAYS_FRESH_NAMES = {'memory-search'}


def docs_budget_allows(stream_path: str) -> bool:
    """Budget walk since the current task started: a FRESH docread (a memory
    name not yet read this task, a credited memory search, or a legacy
    nameless event) refills the budget to GATED_CALL_BUDGET; each 'gated'
    event spends one.

    Re-reading an already-read doc does NOT refill — that is the observed
    budget-farming exploit (re-read one memory between grinds). Freshness
    resets at task start (WF_CLASSIFY re-entry), so a prior task's reads
    never mute the current task's refills.
    """
    budget = 0
    seen = set()
    for event in events_since_task_start(stream_path):
        etype = event.get('type')
        if etype == 'docread':
            name = normalize_memory_name(str(event.get('name') or ''))
            if not name or name in ALWAYS_FRESH_NAMES or name not in seen:
                budget = GATED_CALL_BUDGET
            if name:
                seen.add(name)
        elif etype == 'gated':
            budget -= 1
    return budget > 0


def pending_related_docs(stream_path: str) -> set:
    """Docs surfaced as related links this task ('docpending') and still
    unread — the designated next reads when the budget is spent."""
    surfaced = collect_values_since_task_start(
        stream_path, count_type='docpending', value_key='new')
    read = collect_values_since_task_start(
        stream_path, count_type='docread', value_key='name')
    return surfaced - read


def gate_and_record(stream_path: str) -> bool:
    """Verdict for a gated call; an allowed call depletes the budget by one."""
    if not docs_budget_allows(stream_path):
        return False
    append_event(stream_path, 'gated')
    return True


def build_deny_message(tool_name: str, pending: set = None) -> str:
    """Deny text: budget model, sanctioned clearers, doc-backfill duty.

    When related docs surfaced this task remain unread, they are listed as
    the designated next reads — reading THOSE is the expected refill.
    """
    pending_block = ""
    if pending:
        pending_block = (
            "📚 UNREAD related docs surfaced this task — read these FIRST "
            "(each is a fresh read and refills the budget): "
            + ", ".join(sorted(pending)) + "\n\n"
        )
    return (
        f"📓 DOCS FIRST — {tool_name or 'search'} blocked: docs-consult budget "
        f"spent (one FRESH memory consult clears the next {GATED_CALL_BUDGET} "
        "source reads/searches; re-reading an already-read memory does NOT "
        "refill).\n\n"
        + pending_block +
        "Ops, deploy, and lookup answers live in memories — consult them before "
        "reverse-engineering the codebase (cat/head/grep/git log/Read).\n\n"
        "  1. mcp__plugin_swe_serena__search_memories_by_name(\"<key terms>\") — or "
        "list_memories(topic=\"<prefix>\") / search_memories_by_front_matter\n"
        "  2. mcp__plugin_swe_serena__read_memory(memory_name=\"<hit>\")\n\n"
        f"ANY ONE of those calls refills the budget ({GATED_CALL_BUDGET} more "
        "gated calls) — then re-run this call if the docs did not answer.\n\n"
        "⚠️ Refilling the budget is NOT completed research. Reverse-engineering "
        "source before the feature + standards docs are read is the violation — "
        "not just a spent budget. On a documented subsystem, complete the "
        "WF_CLASSIFY 4d sweep (primary FEATURE_[KEY] + its ARCH_/DOM_/REF_/DEV_ "
        "set); the edit gate stays locked until the sweep is verified in WM. "
        "A memory search that surfaces UNREAD docs grants no credit until they "
        "are read.\n\n"
        "⚠️ If the docs did NOT answer and source discovery was required: ADD "
        "the missing docs — write_memory the discovered facts into the relevant "
        "memory (and index it in MEMORY.md) so the next lookup is answered by "
        "docs, not re-discovery.\n\n"
        "This is the CLAUDE.md '⛔ DOCS FIRST' rule, enforced. See "
        "feedback/FEEDBACK_DOCS_FIRST_ALWAYS."
    )


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        tool_name = get_input_field(input_data, 'tool_name', default='')
        tool_input = input_data.get('tool_input', {})
        if not is_gated_call(tool_name, tool_input):
            output_empty()
            return

        transcript_path = get_input_field(input_data, 'transcript_path', default='')

        # Spawned agents run under <session-uuid>/subagents/agent-<id>.jsonl —
        # extract_session_id resolves them to the PARENT session, whose init
        # sentinel exists, so the no-sentinel exemption below never triggers.
        # Detect the subagent transcript shape directly: never gate them.
        if is_subagent_transcript(transcript_path):
            output_empty()
            return

        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        # Unmanaged sessions have no init sentinel — never gate them.
        if not os.path.exists(get_sentinel_path(session_id)):
            output_empty()
            return

        stream_path = get_stream_path(session_id)
        if not os.path.exists(stream_path):
            output_empty()
            return

        if gate_and_record(stream_path):
            output_empty()
            return

        output_block(build_deny_message(
            tool_name, pending=pending_related_docs(stream_path)))

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Docs-first gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
