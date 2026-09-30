#!/usr/bin/env python3
"""PreToolUse hook for Edit/Write - Validate workflow state for edits.

Ensures edits only happen in appropriate workflow states.
No staleness blocking — checkpoint is informational only.

Orchestrator-drift hard enforcement: in execution states, once all the
existing checks above pass, an additional DRIFT BLOCK applies. When the main
agent's consecutive task-work-since-delegation streak (the same counter
swe_post_orchestrator_drift.py nudges on) reaches
core.stream.DRIFT_HARD_THRESHOLD (12) AND the session's WM file does not
record a 'single-agent: <reason>' override, the edit is DENIED — the
orchestrator must fan the remaining work out to parallel subagents
(FEATURE_SUBAGENTS) instead of continuing to do it directly. Launching a
subagent (an 'Agent'/'Task'/'Workflow' call — a 'delegation' stream event)
resets the counter and unlocks edits immediately.

Spawned agents (Agent/Task tool) are FULLY EXEMPT from this hook's
edit-validation logic — state-gate, sweep-gate, doc-requirement gate, and
drift-block alike — resolved via core.session.is_spawned_agent FIRST in
main(), before any other logic. This exemption does NOT weaken the
bypass-write / raw-memory-write security guards above it, which apply to
every caller, spawned or not. Doc-requirement enforcement for subagents now
happens at DELEGATION time instead (a `[sweep-gate]` check in
swe_pre_agent_model_gate.py denies the Agent/Task call itself when its
prompt lacks the required reading), not on each individual edit.

Per-agent DOC REQUIREMENT gate: applied to the MAIN AGENT ONLY. Before
writing to a file, core.doc_requirements.required_docs_for_path(target,
project_root) is computed (FEATURE_*/DEV_* memories whose front-matter
`paths:` glob matches, plus FEATURE_TESTS/DEV_TESTS for test artifacts) and
diffed against the memories the main agent has actually read this task
(core.stream.collect_values_since_task_start with agent_id=None, so it
counts only main-agent docreads). Any unread required memory DENIES the
edit with a `[doc-gate]` message. `doc_gate_verdict` is kept as a pure,
directly-testable function for this main-agent path.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.session import (
        extract_session_id, is_spawned_agent, get_agent_id,
        find_working_memory_for_session,
    )
    from swe_hooks.core.config import get_project_root, resolve_setup_state
    from swe_hooks.core.stream import (
        get_stream_path, get_feature_sentinel_path,
        collect_values_since_task_start, normalize_memory_name,
        count_task_work_since_delegation, wm_has_single_agent_note,
        DRIFT_HARD_THRESHOLD,
    )
    from swe_hooks.core.doc_requirements import (
        is_test_target as _doc_is_test_target,
        TEST_TARGET_RE, TEST_DOC_NAMES,
        unread_required_docs,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# States where edits are allowed
# WF_VERIFY may edit: verification must fix violations in place.
EDIT_ALLOWED = {'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_CHECKPOINT', 'WF_INITIAL_SETUP', 'WF_ONBOARD', 'WF_VERIFY'}

# States where edits should show a warning
WARN_STATES = {'WF_ARCH_REVIEW', 'WF_RESEARCH'}

# Setup/onboarding states run before any classification — the sweep gate does
# not apply there.
SWEEP_EXEMPT_STATES = {'WF_INITIAL_SETUP', 'WF_ONBOARD'}


def _is_test_target(file_path: str) -> bool:
    """True when the edit target is a test artifact.

    Delegates to core.doc_requirements.is_test_target — single source of
    truth for TEST_TARGET_RE (re-exported above for any caller that still
    references this module's TEST_TARGET_RE directly).
    """
    return _doc_is_test_target(file_path)


def _required_test_docs(project_root: str) -> list:
    """Test-harness memories the project actually documents (files exist).

    Delegates to core.doc_requirements.memory_exists (multi-root aware, via
    memory_roots) instead of this module's own single-root
    .serena/memor(y|ies)/ existence check.
    """
    from swe_hooks.core.doc_requirements import memory_exists
    return [name for name in TEST_DOC_NAMES if memory_exists(name, project_root)]


def _sweep_block_message() -> str:
    return (
        "🛑 SWEEP GATE — edit blocked: the Feature Knowledge Sweep "
        "(WF_CLASSIFY Step 4d) is not verified for THIS task. Refilling the "
        "docs-first budget with one memory read is NOT research.\n"
        "Before the first edit of a task:\n"
        "  1. Enumerate the touched areas' memories: primary FEATURE_[KEY] + "
        "its ARCH_/DOM_/REF_/SYS_ set, MEMORY.md matches, "
        "search_memories_by_name hits\n"
        "  2. read_memory EVERY enumerated memory\n"
        "  3. Record the sweep: swe_wm_update(sections=[{section: \"Affected "
        "Features\", content: \"…\\n- **Memories loaded**: <name>, <name>, "
        "…\"}]) — the list is verified against your ACTUAL reads this task "
        "and unlocks edits.\n"
        "Canon: wf/WF_CLASSIFY Step 4d."
    )


def _test_docs_block_message(unread: list) -> str:
    return (
        "🛑 SWEEP GATE — test-file edit blocked: this project documents its "
        "test harness, and the harness docs were not read this task: "
        f"{', '.join(unread)}.\n"
        "Hand-writing shims/boilerplate without the harness pattern is the "
        "documented failure mode. read_memory each of the above, then retry."
    )


def _sweep_gate_verdict(session_id, tool_input):
    """Deny message when the per-task sweep is unverified, else None.

    Fail-open by design: no session id, no init sentinel (spawned agent /
    unmanaged session), or no stream → not gated. WM_* writes are harness-
    managed and exempt.
    """
    if not session_id:
        return None
    tool_input = tool_input or {}
    target = str(tool_input.get('file_path')
                 or tool_input.get('relative_path') or '')
    if os.path.basename(target.replace('\\', '/')).startswith('WM_'):
        return None

    stream_path = get_stream_path(session_id)
    init_sentinel = os.path.join(
        os.path.dirname(stream_path), f'.init_{session_id}')
    if not os.path.exists(init_sentinel) or not os.path.exists(stream_path):
        return None

    if not os.path.exists(get_feature_sentinel_path(session_id, 'sweep')):
        return _sweep_block_message()

    if _is_test_target(target):
        required = _required_test_docs(get_project_root())
        if required:
            read_names = collect_values_since_task_start(stream_path)
            unread = [n for n in required
                      if normalize_memory_name(n) not in read_names]
            if unread:
                return _test_docs_block_message(unread)
    return None


def _doc_gate_target(tool_input: dict) -> str:
    """Extract the edit target path from a tool_input payload.

    Reuses the same field-precedence as _sweep_gate_verdict: file_path
    (Edit/Write/NotebookEdit) then relative_path (Serena symbolic edit
    tools).
    """
    tool_input = tool_input or {}
    return str(tool_input.get('file_path') or tool_input.get('relative_path') or '')


def _doc_gate_message(target: str, unread: list) -> str:
    """Build the '[doc-gate]' deny message listing each unread required memory
    as a read_memory(...) call, the file it governs, and the retry
    instruction."""
    lines = [
        f"[doc-gate] edit to {target} blocked: required documentation has "
        "not been read this task.",
    ]
    for name in unread:
        lines.append(
            f'  read_memory("{name}") — governs {target}')
    lines.append("Read each memory above, then retry this edit.")
    return "\n".join(lines)


def doc_gate_verdict(target: str, project_root: str, read_names) -> str:
    """Deny message when `target` has unread required documentation, else ''.

    Pure function: target is the file/relative path being edited,
    project_root the resolved project root, read_names the set/iterable of
    memory names already read (normalized or not — unread_required_docs
    normalizes internally). Empty string means "allow". Never raises on a
    target with no matching memories — required_docs_for_path returns [] and
    this returns ''.
    """
    if not target:
        return ''
    unread = unread_required_docs(target, project_root, read_names)
    if not unread:
        return ''
    return _doc_gate_message(target, unread)


def _doc_gate_block(session_id, agent_id, cwd, tool_input):
    """Resolve the doc-requirement gate for this edit, else None.

    Applies to EVERY caller (main agent and every spawned agent), each
    scoped to its OWN docreads this task via
    collect_values_since_task_start(..., agent_id=agent_id) — agent_id=None
    counts only main-agent events, a spawned agent's id counts only that
    agent's own events. WM_* writes are harness-managed and exempt (matches
    the sweep gate's exemption).
    """
    target = _doc_gate_target(tool_input)
    if not target:
        return None
    if os.path.basename(target.replace('\\', '/')).startswith('WM_'):
        return None
    if not session_id:
        return None
    stream_path = get_stream_path(session_id)
    try:
        project_root = get_project_root()
    except Exception:
        project_root = cwd
    read_names = collect_values_since_task_start(stream_path, agent_id=agent_id)
    verdict = doc_gate_verdict(target, project_root, read_names)
    return verdict or None


DRIFT_MANDATE_TEXT = (
    "STOP doing the work yourself. Split the remaining work and launch "
    "parallel subagents NOW (haiku=routine/recon/tests, sonnet=implementation "
    "— FEATURE_SUBAGENTS). For a genuinely tight single-file coupled fix, "
    "record 'single-agent: <reason>' in the WM Context section to continue "
    "solo; the edit gate blocks further edits otherwise."
)


def _drift_block_message(drift_count: int) -> str:
    return (
        f"\U0001f6d1 ORCHESTRATOR DRIFT — edit blocked: {drift_count} direct "
        f"task-work calls without delegating (>= hard threshold "
        f"{DRIFT_HARD_THRESHOLD}).\n\n" + DRIFT_MANDATE_TEXT
    )


def _drift_block_verdict(session_id, cwd):
    """Deny message when the orchestrator-drift hard threshold is hit and the
    session WM carries no 'single-agent: <reason>' override, else None.

    Fail-open by design: no session id, no stream, or no WM file → not
    gated (this specific check only — every other check in this hook is
    unaffected). A 'delegation' stream event resets the counter this reads,
    so launching subagents unlocks edits immediately.
    """
    if not session_id:
        return None
    stream_path = get_stream_path(session_id)
    if not os.path.exists(stream_path):
        return None
    drift_count = count_task_work_since_delegation(stream_path)
    if drift_count < DRIFT_HARD_THRESHOLD:
        return None

    wm_path = find_working_memory_for_session(cwd, session_id)
    if not wm_path:
        return None
    try:
        with open(wm_path, 'r') as f:
            wm_content = f.read()
    except IOError:
        return None
    if wm_has_single_agent_note(wm_content):
        return None

    return _drift_block_message(drift_count)


def _is_bypass_write_attempt(input_data):
    """True if this Edit/Write would enable the project bypass.

    The bypass ("bypass": true in swe-setup-complete.json) may ONLY be set by
    the user via /swe-bypass — never by the assistant, under any rationalization.
    This guard makes it un-settable by an LLM tool call regardless of intent:
    any Edit/Write/write_memory that targets swe-setup-complete.json AND
    introduces a truthy bypass is hard-blocked here, before the state check.
    """
    tool_input = input_data.get('tool_input', {}) or {}
    target = (
        tool_input.get('file_path')
        or tool_input.get('memory_name')
        or ''
    )
    if 'swe-setup-complete' not in str(target):
        return False
    # Gather any content this call would write.
    blob = ' '.join(str(tool_input.get(k, '')) for k in (
        'content', 'new_string', 'new_str', 'replacement', 'repl',
    ))
    normalized = blob.replace(' ', '').replace("'", '"').lower()
    # Match "bypass":true / "bypass": true (whitespace/quote-insensitive)
    return '"bypass":true' in normalized


def _is_raw_memory_write(input_data):
    """True if a raw Edit/Write targets a Serena memory file.

    Memory files under .serena/memory/ and .serena/memories/ must be edited
    via Serena's write_memory/edit_memory tools (which keep frontmatter,
    indexing hooks, and sync behavior intact) — never via raw Edit/Write.
    Exception: session Working Memory (WM_*.md), which the harness/daemon
    writes with the Write tool by design.
    """
    if input_data.get('tool_name', '') not in ('Edit', 'Write'):
        return False
    file_path = str((input_data.get('tool_input') or {}).get('file_path', ''))
    norm = file_path.replace('\\', '/')
    if '/.serena/memory/' not in norm and '/.serena/memories/' not in norm:
        return False
    return not os.path.basename(norm).startswith('WM_')


def _block_message(current):
    """Build the edit-block message, tailored to the blocking state.

    WF_CLASSIFY is the common case: the assistant tried to edit the target file
    before routing. The message explains WHY (classification-only state) and what
    to do (finish routing, then transition) so it self-corrects instead of
    retrying the same blocked edit.
    """
    if current == 'WF_CLASSIFY':
        return (
            "🛑 Edit blocked in WF_CLASSIFY — this is a classification/routing "
            "state, not an execution state. No edits happen here.\n"
            "You do NOT need to open or edit the target file to classify the task. "
            "Finish routing first:\n"
            "  1. Classify task type + count files touched (Step 3 / 3b)\n"
            "  2. Load the primary FEATURE_[KEY] (Step 4)\n"
            "  3. Transition: minor patch (≤5 files) → WF_EXECUTE; "
            "new feature / >5 files → WF_ARCH_REVIEW\n"
            "Then make the edit in WF_EXECUTE."
        )
    return (
        f"🛑 Edit blocked in state {current}. Edits are only allowed in "
        f"WF_EXECUTE / WF_DEBUG_TDD / WF_CHECKPOINT / WF_VERIFY. "
        f"Transition to WF_EXECUTE first."
    )


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # Spawned-agent status is resolved FIRST (matching
        # swe_pre_search_docs_gate.py's exemption order) so the drift block
        # below can consult it — spawned agents are expected to do direct
        # work and must NEVER hit that block. It does NOT bypass the
        # security guards immediately below (bypass-write / raw-memory-write
        # apply to every caller, spawned or not).
        spawned_agent = is_spawned_agent(input_data)

        # HARD GUARD (runs before any state logic): the assistant may NEVER
        # set the project bypass. Only the user, via /swe-bypass, can do that.
        if _is_bypass_write_attempt(input_data):
            output = HookOutput(event_name="PreToolUse")
            output.block(
                "🛑 BLOCKED: the SWE workflow bypass can only be enabled by the "
                "user via the /swe-bypass command — never by the assistant.\n"
                "Do not edit swe-setup-complete.json to add \"bypass\": true. "
                "If the user wants to disable the workflow, tell them to run "
                "/swe-bypass themselves."
            )
            output.output_and_exit()
            return

        # Project-level bypass: if "bypass": true in swe-setup-complete.json,
        # skip the state-based edit gate entirely — same as the init gate does.
        # Runs AFTER the hard-guard above so a bypassed project still cannot have
        # the assistant flip the flag further. SessionStart announces the bypass.
        try:
            project_root = get_project_root()
            if resolve_setup_state(project_root).get('bypassed'):
                output_status("✓ Edit allowed (bypassed)", event="PreToolUse")
                return
        except Exception:
            pass  # bypass check is best-effort; fall through to state gate

        # Raw Edit/Write on Serena memory files: always denied (state-independent).
        # Memories are edited via write_memory/edit_memory; WM_* files are exempt.
        if _is_raw_memory_write(input_data):
            output = HookOutput(event_name="PreToolUse")
            output.block(
                "🛑 BLOCKED: raw Edit/Write on a Serena memory file.\n"
                "Files under .serena/memory(ies)/ must be modified via Serena's "
                "memory tools:\n"
                "  - mcp__plugin_swe_serena__edit_memory(memory_name, needle, repl, mode)\n"
                "  - mcp__plugin_swe_serena__write_memory(memory_name, content)  # full rewrite\n"
                "Address the memory by its logical name (e.g. \"feature/FEATURE_X\"), "
                "not its file path."
            )
            output.output_and_exit()
            return

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        agent_id = get_agent_id(input_data)

        # Spawned agents: fully exempt from edit validation. No sweep
        # sentinel, no doc-requirement gate, no drift block, no
        # workflow-state denial — subagents are instructed to bypass
        # WF_INIT and do direct work. Doc-requirement enforcement for
        # subagents is applied at DELEGATION time instead (see
        # swe_pre_agent_model_gate.py's [sweep-gate]), not per-edit.
        if spawned_agent:
            output_status("✓ Edit allowed (spawned agent)", event="PreToolUse")
            return

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)
        current = state_mgr.get_current_state()

        # Allow edits in execution states — but only once the per-task
        # Feature Knowledge Sweep is verified (sweep sentinel exists).
        if current in EDIT_ALLOWED:
            if current not in SWEEP_EXEMPT_STATES:
                verdict = _sweep_gate_verdict(
                    session_id, input_data.get('tool_input', {}))
                if verdict:
                    output = HookOutput(event_name="PreToolUse")
                    output.block(verdict)
                    output.output_and_exit()
                    return

            # Per-agent doc-requirement gate: applies to the main agent too,
            # in addition to (not instead of) the sweep-gate's own test-docs
            # check above. agent_id=None here, so collect_values_since_task_
            # start counts only main-agent docreads.
            doc_verdict = _doc_gate_block(
                session_id, agent_id, cwd, input_data.get('tool_input', {}))
            if doc_verdict:
                output = HookOutput(event_name="PreToolUse")
                output.block(doc_verdict)
                output.output_and_exit()
                return

            # Orchestrator-drift HARD enforcement: runs AFTER every check
            # above passes, never weakening them. Spawned agents are exempt
            # (core.session.is_spawned_agent, resolved above) — they are
            # expected to do direct work and must never hit this block.
            if not spawned_agent:
                drift_verdict = _drift_block_verdict(session_id, cwd)
                if drift_verdict:
                    output = HookOutput(event_name="PreToolUse")
                    output.block(drift_verdict)
                    output.output_and_exit()
                    return

            output_status(f"✓ Edit allowed ({current})", event="PreToolUse")
            return

        # Warn but allow in planning states
        if current in WARN_STATES:
            output = HookOutput(event_name="PreToolUse")
            output.add_message(f"⚠️ Edit in planning state: {current}")
            output.output_and_exit()
            return

        # BLOCK: editing not allowed in this state
        output = HookOutput(event_name="PreToolUse")
        output.block(_block_message(current))
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Pre-edit error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
