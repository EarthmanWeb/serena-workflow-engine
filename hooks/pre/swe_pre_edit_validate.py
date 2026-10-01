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
diffed against the memories the main agent has actually read THIS SESSION
(core.stream.collect_values_session with agent_id=None, so it counts only
main-agent docreads, across the WHOLE session — not just the current task).
Any unread required memory DENIES the edit with a `[doc-gate]` message.
`doc_gate_verdict` is kept as a pure, directly-testable function for this
main-agent path. (The sweep gate's own task-scoped test-docs check, and
every other sweep/drift check in this hook, are UNCHANGED — only the
doc-gate's read set widened to session scope.)

TARGET-PATH EXTRACTION: every target-path extraction in this hook
(sweep-gate, doc-gate) goes through the single helper `_extract_target_path`
— precedence file_path, then notebook_path, then relative_path. hooks.json's
matcher covers Edit/Write/NotebookEdit/MultiEdit and the Serena symbolic
edit tools (create_text_file/replace_lines/delete_lines/insert_at_line/
replace_in_files/replace_symbol_body/replace_content/
insert_before_symbol/insert_after_symbol); Claude Code's NotebookEdit sends
its target under `notebook_path`, NOT `file_path` — a prior version of this
hook read only file_path/relative_path, so a NotebookEdit target silently
resolved to '' and every gate below (sweep, doc) skipped it. Never
re-derive this precedence list ad hoc at a new call site — call
`_extract_target_path`.

BASH WRITES are treated as edits: core.memory_fs.bash_write_targets(command)
extracts the paths a Bash command writes; each target resolved against the
hook's cwd and kept only when inside the project root (excluding
.serena/** and .git/**, already covered by swe_pre_memory_fs_gate.py). A
Bash call with no in-project write target returns {} immediately (this hook
now runs on every Bash call, so the no-op path stays silent and fast). A
Bash call WITH an in-project write target runs the exact same
planning-state/sweep-sentinel/drift-block/doc-gate checks as an Edit to each
target, with the same main-agent/spawned-agent exemptions; a `replace_in_files`
target that is a directory or empty skips the doc-gate (state/sweep/drift
still apply) since there is no single file to compute required docs for.
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
        collect_values_since_task_start, collect_values_session,
        normalize_memory_name,
        count_task_work_since_delegation, wm_has_single_agent_note,
        DRIFT_HARD_THRESHOLD,
    )
    from swe_hooks.core.doc_requirements import (
        is_test_target as _doc_is_test_target,
        TEST_TARGET_RE, TEST_DOC_NAMES,
        unread_required_docs,
    )
    from swe_hooks.core import memory_fs
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


def _extract_target_path(tool_input: dict) -> str:
    """Extract the edit target path from a tool_input payload.

    SINGLE SOURCE OF TRUTH for target-path precedence in this hook — every
    other extraction site (sweep gate, doc gate) calls this instead of
    re-deriving its own precedence list.

    Field precedence: file_path (Edit/Write/MultiEdit) then notebook_path
    (Claude Code's NotebookEdit sends the path under this key, NOT
    file_path — commit 91f3c70 added NotebookEdit to this hook's matcher
    without widening target extraction, so NotebookEdit targets silently
    resolved to '' and skipped every gate below) then relative_path (Serena
    symbolic edit tools: replace_symbol_body, replace_content,
    insert_before_symbol, insert_after_symbol, create_text_file,
    replace_lines, delete_lines, insert_at_line, replace_in_files —
    relative_path may be a directory or empty for replace_in_files, handled
    by the doc-gate skip in _doc_gate_block).
    """
    tool_input = tool_input or {}
    return str(
        tool_input.get('file_path')
        or tool_input.get('notebook_path')
        or tool_input.get('relative_path')
        or ''
    )


def _sweep_gate_verdict(session_id, tool_input):
    """Deny message when the per-task sweep is unverified, else None.

    Fail-open by design: no session id, no init sentinel (spawned agent /
    unmanaged session), or no stream → not gated. WM_* writes are harness-
    managed and exempt.
    """
    if not session_id:
        return None
    target = _extract_target_path(tool_input)
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

    Delegates to _extract_target_path — single source of truth for target
    extraction in this hook (file_path, then notebook_path, then
    relative_path).
    """
    return _extract_target_path(tool_input)


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

    Called on the MAIN AGENT path only (callers pass agent_id=None here —
    spawned-agent edits never reach this function, see main()). Reads are
    scoped to the WHOLE SESSION via collect_values_session (operator
    decision: dev-standards reads count per session, not per task) — a
    memory read earlier in the session satisfies the doc-gate for a later
    task's edit to a file it governs. WM_* writes are harness-managed and
    exempt (matches the sweep gate's exemption).

    A target that resolves to a directory or is empty (replace_in_files with
    a directory/empty relative_path) skips the doc-gate entirely — there is
    no single file to compute required docs for; state/sweep/drift checks
    in main() still apply independently of this function.
    """
    target = _doc_gate_target(tool_input)
    if not target:
        return None
    if os.path.basename(target.replace('\\', '/')).startswith('WM_'):
        return None
    if not session_id:
        return None
    try:
        project_root = get_project_root()
    except Exception:
        project_root = cwd
    abs_target = target if os.path.isabs(target) else os.path.join(cwd or project_root, target)
    if os.path.isdir(abs_target):
        return None
    stream_path = get_stream_path(session_id)
    read_names = collect_values_session(stream_path, agent_id=agent_id)
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
    writes with the Write tool by design (memory_fs.is_memory_store_path
    carries the same WM_* carve-out).

    Delegates to memory_fs.is_memory_store_path, which ALSO matches the
    auto-memory symlink target (~/.claude/projects/<encoded>/memory ->
    <project>/.serena/memory) via os.path.realpath — a raw Edit/Write
    through that symlink is caught too, not just the direct .serena/ path.
    """
    if input_data.get('tool_name', '') not in ('Edit', 'Write'):
        return False
    file_path = str((input_data.get('tool_input') or {}).get('file_path', ''))
    cwd = input_data.get('cwd') or os.getcwd()
    return memory_fs.is_memory_store_path(file_path, cwd)


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


def _in_project_bash_targets(command: str, cwd: str, project_root: str) -> list:
    """Bash write targets (memory_fs.bash_write_targets) resolved against
    `cwd`, filtered to those INSIDE `project_root`, excluding
    <root>/.serena/** and <root>/.git/** (memory stores are already handled
    by swe_pre_memory_fs_gate.py — this hook must not duplicate that gate).
    A target outside the project root (/tmp, scratchpad, ~) is dropped
    silently — it is not this hook's concern. Returns resolved absolute
    paths, de-duplicated, in order of first appearance.
    """
    raw_targets = memory_fs.bash_write_targets(command)
    if not raw_targets:
        return []
    root = os.path.abspath(project_root)
    serena_prefix = os.path.join(root, '.serena') + os.sep
    git_prefix = os.path.join(root, '.git') + os.sep
    resolved = []
    seen = set()
    for target in raw_targets:
        expanded = os.path.expanduser(target)
        abs_target = expanded if os.path.isabs(expanded) else os.path.join(cwd or root, expanded)
        abs_target = os.path.normpath(abs_target)
        if not (abs_target == root or abs_target.startswith(root + os.sep)):
            continue
        if abs_target.startswith(serena_prefix) or abs_target == root + '/.serena':
            continue
        if abs_target.startswith(git_prefix) or abs_target == root + '/.git':
            continue
        if abs_target not in seen:
            seen.add(abs_target)
            resolved.append(abs_target)
    return resolved


def _run_edit_checks_for_target(session_id, agent_id, cwd, target, current,
                                 spawned_agent):
    """Run the SAME checks, in the SAME order, as main()'s EDIT_ALLOWED
    branch applies to a direct Edit/Write/Serena call — but against a
    single TARGET path instead of the tool_input payload. Shared by both
    the direct-edit path (main()) and the Bash-write path
    (_bash_write_gate_verdict) so neither duplicates the other's gate
    semantics.

    Order: sweep-sentinel + test-docs (skipped entirely in
    SWEEP_EXEMPT_STATES) -> doc-gate -> drift hard block (spawned agents
    exempt). Returns a deny message string, or None to allow.
    """
    pseudo_input = {'file_path': target}

    if current not in SWEEP_EXEMPT_STATES:
        verdict = _sweep_gate_verdict(session_id, pseudo_input)
        if verdict:
            return verdict

    doc_verdict = _doc_gate_block(session_id, agent_id, cwd, pseudo_input)
    if doc_verdict:
        return doc_verdict

    if not spawned_agent:
        drift_verdict = _drift_block_verdict(session_id, cwd)
        if drift_verdict:
            return drift_verdict

    return None


def _bash_write_gate_verdict(session_id, agent_id, cwd, current, spawned_agent,
                              command, project_root):
    """Resolve the full Bash-write-as-edit gate for a Bash tool_input, else
    None (allow — includes the no-op "nothing writes into the project"
    case, which must stay silent and fast since this hook now runs on every
    Bash call).

    Mirrors main()'s Edit/Write handling exactly: planning-state block
    (_block_message / WARN_STATES pass-through), then per in-project write
    target (in order) the SAME sweep/doc-gate/drift checks an Edit to that
    file would get (_run_edit_checks_for_target) — the FIRST target whose
    checks deny wins (an "edit" to any one of several targets in the same
    Bash call is enough to block the whole call, matching how a single Edit
    call targets exactly one file). Same main-agent/spawned-agent exemptions
    as every other check in this hook.
    """
    targets = _in_project_bash_targets(command, cwd, project_root)
    if not targets:
        return None

    if current not in EDIT_ALLOWED:
        if current in WARN_STATES:
            return None  # warn-but-allow states: no block for Bash either
        return _block_message(current)

    for target in targets:
        verdict = _run_edit_checks_for_target(
            session_id, agent_id, cwd, target, current, spawned_agent)
        if verdict:
            return (
                f"🛑 Bash write to {target} is treated as an edit.\n\n"
                + verdict
            )
    return None


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

        tool_name = get_input_field(input_data, 'tool_name', default='')
        if tool_name == 'Bash':
            # BASH WRITES are treated as edits (see module docstring). Fast
            # path: no in-project write target -> {} immediately, since this
            # hook now runs on EVERY Bash call and must stay silent/cheap for
            # the overwhelming majority (non-writing) of them.
            command = str((input_data.get('tool_input') or {}).get('command', ''))
            try:
                bash_project_root = get_project_root()
            except Exception:
                bash_project_root = cwd
            bash_verdict = _bash_write_gate_verdict(
                session_id, agent_id, cwd, current, spawned_agent,
                command, bash_project_root)
            if bash_verdict:
                output = HookOutput(event_name="PreToolUse")
                output.block(bash_verdict)
                output.output_and_exit()
                return
            # No in-project write target, or every check passed: silent allow.
            print(json.dumps({}), file=sys.stdout)
            sys.exit(0)
            return

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
