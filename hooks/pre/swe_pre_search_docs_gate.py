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
    awk/sed and git status/diff/log/show/blame) as the PRIMARY command of any
    `;`/`&&`-sequenced group — mutation/build/test commands are NOT gated,
    including when their output is piped through head/tail/grep filters
  - Container recon ("digging in Docker"): `docker exec` / `docker compose
    exec` whose executed command reverse-engineers the running stack —
    grep/sed/cat/env recon or `php -r` inline probes of wp-config /
    object-cache / redis / env wiring INSIDE the container. The first token
    is `docker`, so the inspection classifier above never sees it; this
    catches it. Container up/down/build/restart and `docker exec … wp …`
    (the WP-CLI-MCP path) are NOT recon.

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

Undocumented code areas: when no reasonable feature memories exist for the
area under research, the deny message routes the agent to delegate indexing
to a FOREGROUND Agent running /swe-feature-onboard (or /swe-feature-update
for stale docs), wait for it, then read the memories it wrote — continued
manual grepping is explicitly NOT the remedy.

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
        get_stream_path, get_sentinel_path, get_feature_sentinel_path,
        append_event, events_since_task_start, collect_values_since_task_start,
        normalize_memory_name,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


# One docs consult clears the gate for this many gated calls. The default
# (docread → base) is generous: a single relevant memory read buys a long run
# of source reads, so a well-scoped task rarely re-hits the gate.
GATED_CALL_BUDGET = 15

# A WM-verified WF_CLASSIFY 4d sweep (the '.sweep_feature_<session>' sentinel,
# created ONLY when the Affected-Features "Memories loaded" list was validated
# against this task's actual docreads) is PROOF the agent read the primary
# feature + its arch/dom/ref set. When present, top the budget up ONCE by this
# much so an agent that has provably done its research keeps source access
# through execution — instead of hunting for a fresh, unrelated memory to
# re-arm. Credited exactly once per task via a 'sweep_bonus' stream marker;
# the sweep sentinel is cleared on every WF_CLASSIFY re-entry, so it cannot
# farm across tasks.
SWEEP_BONUS = 40

# Bash inspection classification — by command GROUP, judged on the group's
# FIRST pipeline stage:
#   - Groups are split on `;`, `&&`, `||`, `&`, newline. Each group is a
#     standalone command: a `;`/`&&`-sequenced `cat`/`grep` after a build IS
#     recon and gates.
#   - Within a group, only the FIRST pipe stage classifies it. A work command
#     whose output is piped through head/tail/grep is still work — the filter
#     reads the command's own output, not the codebase. `pytest … | tail`,
#     `composer test | grep FAIL`, `phpcbf … | head` must NOT gate; pure recon
#     pipelines (`ls … | head`, `find … | grep`) still do.
#   - Leading VAR=value assignments on a stage are stripped before matching.
#   - EXCEPTION: an inspection group whose ONLY path operand is a transient
#     OUTPUT path (/tmp, /var/tmp, $TMPDIR, /dev/…) is result-inspection, not
#     codebase recon — that file is command output, never source. So
#     `grep … /tmp/test-pp.log` after a test run does NOT gate. Absolute paths
#     that are NOT transient (a repo checkout under /Users, /x, …) still gate.
# Mutation, build, and test commands are deliberately absent: they do work.
BASH_GROUP_SPLIT_RE = re.compile(r'(?:;|&&|\|\||&|\n)+')
BASH_PIPE_SPLIT_RE = re.compile(r'\|(?!\|)')
BASH_ENV_ASSIGN_RE = re.compile(
    r'^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S*)\s+)*')
BASH_INSPECT_FIRST_RE = re.compile(
    r'^(?:'
    r'(?:cat|head|tail|less|more|grep|rg|find|ls|tree|awk|sed)\b'
    r'|git\s+(?:status|diff|log|show|blame)\b'
    r')',
    re.IGNORECASE,
)
# Transient OUTPUT locations — a file here is command output, never source, so
# an inspection group reading ONLY such a path is result-inspection, not recon.
BASH_TRANSIENT_PATH_RE = re.compile(
    r'(?:^|[\s"\'=(])(?:/tmp/|/var/tmp/|/dev/|/private/(?:tmp|var)/|\$\{?TMPDIR\}?/)')
# Any explicit filesystem path operand (absolute, ./…, ../…, or a bare
# dir/file token). Used to decide whether an inspection group targets ONLY
# transient output vs. reaches into the tree.
BASH_PATH_OPERAND_RE = re.compile(r'(?:^|[\s"\'=(])(?:/|\./|\.\./|\$\{?TMPDIR\}?/)')

# Container recon ("digging in Docker"): reverse-engineering the running stack
# by hand-grepping its filesystem / config / env INSIDE the container instead
# of consulting docs or the WP-CLI / QM / sps_log tooling. The canonical field
# violation: an agent debugging a blank page runs a chain of
# `docker exec <c> sh -c 'grep … wp-config.php'`, `sed -n … wp-config.php`,
# `php -r 'var_dump(getenv("PANTHEON_ENVIRONMENT")…)'` to spelunk redis /
# object-cache / env wiring. The group's first token is `docker`, so
# BASH_INSPECT_FIRST_RE never matches — this pair classifies the recon that
# runs inside the container.
#
# Gated: `docker exec` / `docker[- ]compose exec` whose executed payload is
#   - a recon binary run directly or via `sh -c` / `bash -c`
#     (grep/sed/cat/head/tail/less/more/awk/find/ls/tree/env/printenv/rg), OR
#   - `php -r` / `php -d … -r` inline probes (getenv/$_ENV/$_SERVER/define
#     introspection of the running config).
# NOT gated: container mutation/build/lifecycle (up/down/build/restart/cp) and
# `docker exec … wp …` — raw WP-CLI is the block-wordpress-exec / WP-CLI-MCP
# concern, not docs recon.
BASH_DOCKER_EXEC_RE = re.compile(
    r'\bdocker(?:[-\s]+compose)?\s+exec\b', re.IGNORECASE)
BASH_CONTAINER_RECON_RE = re.compile(
    r'(?:'
    r'(?:sh|bash)\s+-c\b.*?'
    r'(?:cat|head|tail|less|more|grep|rg|find|ls|tree|awk|sed|env|printenv)\b'
    r'|(?:^|[\s\'"])(?:cat|head|tail|less|more|grep|rg|find|ls|tree|awk|sed|'
    r'env|printenv)(?:\s|$)'
    r'|php\s+(?:-[A-Za-z]\S*\s+|[A-Za-z_][\w.=]*\s+)*-r\b'
    r')',
    re.IGNORECASE | re.DOTALL,
)


def _is_container_recon(group: str) -> bool:
    """True when a command group is `docker exec`-style container recon.

    Digging inside the running container (grep/sed/cat/php -r probing
    wp-config, object-cache, redis, env) is reverse-engineering the stack —
    the docs / WP-CLI MCP / QM / sps_log answer it. Container
    mutation/build/lifecycle and raw `docker exec … wp` are NOT recon.
    """
    if not BASH_DOCKER_EXEC_RE.search(group):
        return False
    # The portion after `exec` is what runs in the container.
    payload = BASH_DOCKER_EXEC_RE.split(group, 1)[-1]
    return bool(BASH_CONTAINER_RECON_RE.search(payload))


def _inspects_only_transient(group: str) -> bool:
    """True when an inspection group's only path operands are transient output.

    `grep … /tmp/run.log`, `cat "$TMPDIR/out"`, `tail /dev/stdin` inspect
    produced output, not the codebase, so they must NOT gate. A group that also
    reaches a non-transient path (`grep -rn X /Users/…/src`) still gates.
    """
    if not BASH_TRANSIENT_PATH_RE.search(group):
        return False
    # Every path-like operand must be transient. Strip the transient ones, then
    # look for any remaining filesystem path (a non-transient target).
    remainder = BASH_TRANSIENT_PATH_RE.sub(' ', group)
    return not BASH_PATH_OPERAND_RE.search(remainder)


def bash_is_inspection(command: str) -> bool:
    """True when any command group's first pipeline stage is inspection/recon,
    or the group is `docker exec`-style container recon."""
    for group in BASH_GROUP_SPLIT_RE.split(command or ''):
        if _is_container_recon(group):
            return True
        first_stage = BASH_PIPE_SPLIT_RE.split(group, 1)[0].strip()
        first_stage = BASH_ENV_ASSIGN_RE.sub('', first_stage)
        if BASH_INSPECT_FIRST_RE.match(first_stage):
            # Judge the transient-vs-recon question on the WHOLE group: a `\|`
            # inside a quoted grep pattern otherwise splits the path off the
            # first pipe stage. A single-stage group == first_stage.
            if _inspects_only_transient(group.strip()):
                continue
            return True
    return False


def is_gated_call(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call is a docs-first-gated code-surf.

    Grep/Glob/search_for_pattern: always gated.
    Bash: gated only when a command group's PRIMARY (first-stage) command is
    inspection/recon. Mutation/build/test commands pass through, including
    when their output is piped through pagination/filter stages.
    Read: NEVER gated — opening a specific known file is not surfing.
    Anything else: not gated.
    """
    tool_input = tool_input or {}
    if tool_name in ('Grep', 'Glob') or tool_name.endswith('search_for_pattern'):
        return True
    if tool_name == 'Bash':
        return bash_is_inspection(str(tool_input.get('command', '')))
    return False


# docread names that refill even when repeated: credited memory searches
# (a search confirming already-read docs is the sanctioned re-consult).
ALWAYS_FRESH_NAMES = {'memory-search'}


def _session_id_from_stream(stream_path: str) -> str:
    """Recover the session id from a stream path ('<dir>/<session>.jsonl').

    The budget walk needs it to locate the sibling sweep sentinel. Keeping the
    public signature as (stream_path) means every existing caller and test is
    unaffected — a stream with no sibling sentinel simply earns no bonus.
    """
    base = os.path.basename(stream_path)
    return base[:-6] if base.endswith('.jsonl') else base


def sweep_verified(stream_path: str) -> bool:
    """True when this task's WM-verified 4d-sweep sentinel exists."""
    session_id = _session_id_from_stream(stream_path)
    if not session_id:
        return False
    return os.path.exists(get_feature_sentinel_path(session_id, 'sweep'))


def docs_budget_allows(stream_path: str) -> bool:
    """Budget walk since the current task started: a FRESH docread (a memory
    name not yet read this task, a credited memory search, or a legacy
    nameless event) refills the budget to GATED_CALL_BUDGET; each 'gated'
    event spends one. A 'sweep_bonus' marker (stamped once by gate_and_record
    when the WM-verified sweep sentinel is present) adds SWEEP_BONUS on top.

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
        elif etype == 'sweep_bonus':
            budget += SWEEP_BONUS
        elif etype == 'gated':
            budget -= 1
    return budget > 0


def _sweep_bonus_credited(stream_path: str) -> bool:
    """True when the one-time sweep top-up was already stamped this task."""
    for event in events_since_task_start(stream_path):
        if event.get('type') == 'sweep_bonus':
            return True
    return False


def pending_related_docs(stream_path: str) -> set:
    """Docs surfaced as related links this task ('docpending') and still
    unread — the designated next reads when the budget is spent."""
    surfaced = collect_values_since_task_start(
        stream_path, count_type='docpending', value_key='new')
    read = collect_values_since_task_start(
        stream_path, count_type='docread', value_key='name')
    return surfaced - read


def gate_and_record(stream_path: str) -> bool:
    """Verdict for a gated call; an allowed call depletes the budget by one.

    Before judging, credit the one-time sweep top-up: if this task's 4d-sweep
    sentinel is present and the bonus was not already stamped, append a single
    'sweep_bonus' marker. This makes the credit available on the FIRST gated
    call after a verified sweep and, being a stream event, exactly once per
    task (the sentinel is cleared on WF_CLASSIFY re-entry).
    """
    if sweep_verified(stream_path) and not _sweep_bonus_credited(stream_path):
        append_event(stream_path, 'sweep_bonus')
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
        f"refill). A WM-verified WF_CLASSIFY 4d sweep tops this up by "
        f"{SWEEP_BONUS} once per task — if you have not completed the sweep, "
        "that is the real refill here, not another lone read.\n\n"
        + pending_block +
        "Ops, deploy, and lookup answers live in memories — consult them before "
        "reverse-engineering the codebase (cat/head/grep/git log/Read).\n\n"
        "  1. mcp__plugin_swe_serena__search_memories_by_name(\"<key terms>\") — or "
        "list_memories(topic=\"<prefix>\") / search_memories_by_front_matter\n"
        "  2. mcp__plugin_swe_serena__read_memory(memory_name=\"<hit>\")\n\n"
        f"ANY ONE of those calls refills the budget ({GATED_CALL_BUDGET} more "
        "gated calls) — then re-run this call if the docs did not answer.\n\n"
        "🚫 NO reasonable feature memories for this code area (both searches "
        "return nothing relevant)? Do NOT continue grepping manually. FIRST "
        "STEP: delegate indexing to a FOREGROUND agent —\n"
        "  Agent(prompt=\"You are a subagent. BYPASS WF_INIT. Run the "
        "/swe-feature-onboard skill for <area>\", description=\"Onboard "
        "<area> feature\")\n"
        "(use /swe-feature-update instead when the feature exists but its "
        "docs are stale/incomplete). Do NOT set run_in_background — WAIT for "
        "the agent to complete, THEN read the FEATURE_/ARCH_/DOM_/REF_ "
        "memories it wrote. Those fresh reads clear this gate, and the new "
        "docs — not manual grepping — are what your work continues from.\n\n"
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
