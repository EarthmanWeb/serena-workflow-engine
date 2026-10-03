#!/usr/bin/env python3
"""PostToolUse hook (matcher ".*") — orchestrator-drift nudge.

Sums WEIGHTED direct task-work calls made by the MAIN agent since the last
background delegation in this session (see drift_weight):
  - FULL_WEIGHT (1.0): Edit/Write/NotebookEdit/MultiEdit, Serena edit tools,
    mutating Bash, foreground Agent/Task.
  - LOW_WEIGHT (0.0): Read/Grep/Glob/WebFetch and every other built-in,
    verification/inspection Bash (bash_is_verification), and every
    non-delegation MCP tool (Serena read/symbol tools, jira, browser, wp-cli…)
    — the 0.5 class was dropped (read-heavy research work was the main
    false-positive driving hard blocks; see DRIFT_THRESHOLD comment).
  - EXEMPT (0, nothing logged): workflow machinery — Serena memory tools,
    swe-wm MCP tools, ToolSearch, AskUserQuestion, TodoWrite, Skill,
    SendMessage.
At DRIFT_THRESHOLD (6) of weighted sum, nudges the orchestrator to stop
doing the work itself and split what remains into parallel subagents — the
"orchestrator + swarm delegation" model this session is meant to follow
(FEATURE_SUBAGENTS). At DRIFT_HARD_THRESHOLD (12), the advisory escalates
into a MANDATE: split remaining work into parallel subagents NOW, or record a
NEW 'single-agent: <reason>' override in the WM Context section — the sibling
PreToolUse edit gate (swe_pre_edit_validate.py) hard-enforces this same
threshold by DENYING further edits unless a single-agent line was written
AFTER the hard block (pre-emptive notes never count; the disarm ends at the
next background delegation).

A delegation resets the streak (the orchestrator just handed work off) ONLY
when it is a real hand-off the orchestrator is not blocking on:
  - a Workflow call (always background), or
  - an Agent/Task call with tool_input['run_in_background'] exactly True.
A FOREGROUND Agent/Task call (run_in_background missing or False) is NOT a
reset — the orchestrator spawned one agent and is waiting on it, which is
exactly the single-threaded pattern this nudge exists to discourage. It is
instead recorded as ordinary task_work (same counting path as Edit/Bash/etc,
including the advisory/hard-threshold escalation), with a status message
telling the orchestrator to relaunch with run_in_background: true.
See `is_background_delegation` for the exact rule.

Exempt when the calling tool itself IS a real (background) Agent/Workflow
launch — that event is the reset marker, not task work, and is recorded as
'delegation' instead of 'task_work' by this same hook (registered on both
matchers so one script covers count + reset).

A Bash call whose every command group is verification/inspection (git
status/diff/log/show/commit/add, test runners, py_compile, jq ., validate-*.py,
grep/rg/cat/head/tail/ls/find/sed -n/awk/diff…) counts at LOW_WEIGHT, not
zero: a long read/inspect loop in the orchestrator IS drift (12 reads = 6 =
advisory), just slower-accruing than edits.

On reaching DRIFT_HARD_THRESHOLD this hook also logs the 'drift_hard_block'
snapshot event (core.stream.record_drift_hard_block) so a single-agent note
written after the mandate message disarms the edit gate, while a note that
pre-dates it never does.

Scope-guard event logging (core.scope_guard — see that module's docstring
for the full event vocabulary): this hook is also where the remaining scope-
guard events get appended, alongside its drift-counting duty.

  - Spawned-agent branch: a spawned agent's tool call that classify_kind()
    recognizes (an edit, a test run, or plain Bash) logs `agent_ok` for that
    agent+kind — PostToolUse only fires on tool SUCCESS, so every call this
    hook sees for a spawned agent already succeeded. A failed call routes to
    PostToolUseFailure instead (swe_post_tool_failure.py logs `agent_fail`
    there).
  - Main-agent Agent/Task call: extracts the newly spawned agent's id from
    the call's tool_response (see extract_spawned_agent_id) and logs
    `agent_spawn` with a resolved budget — a `[swe-budget: N]` tag in the
    spawning prompt (scope_guard.parse_budget_tag) overrides the model-
    family default (scope_guard.budget_for_model). No id extractable -> no
    event (the scope guard then uses DEFAULT_BUDGET for that agent). When
    the spawning prompt signals expected failing test runs (scope_guard.
    expects_red_runs — a literal `[swe-expect-red]` tag or fail-proofing/
    red-green phrasing), the event also carries `expect_red: true`, which
    scope_guard.scope_state/scope_verdict use to widen the 'test' failure-
    streak limit for that agent only.
  - Main-agent SendMessage call: a `[scope-extend]` tag in the message
    (scope_guard.parse_scope_extend) logs `scope_extend` against the
    message's `to` agent. SendMessage is neither task work nor a delegation
    for DRIFT counting purposes — it never resets or advances the drift
    streak, regardless of whether it carries a scope-extend tag.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_status, output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import (
        extract_session_id, is_spawned_agent, is_subagent_transcript,
        get_agent_id, find_working_memory_for_session,
    )
    from swe_hooks.core.stream import (
        get_stream_path, append_event, count_task_work_since_delegation,
        has_event_since_last, format_drift_weight, record_drift_hard_block,
        DRIFT_HARD_THRESHOLD,
    )
    from swe_hooks.core.scope_guard import (
        classify_kind, budget_for_model, parse_budget_tag, parse_scope_extend,
        is_test_command, expects_red_runs,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)

# Weighted direct task-work sum before the advisory drift nudge.
DRIFT_THRESHOLD = 6

# Per-call drift weights (see module docstring / drift_weight).
# Measured motivation: after reads/MCP were weighted 0.5, hard blocks went
# 2 -> 446 per era while delegation (Agent calls) stayed flat 184 -> 186 —
# pure friction from read-heavy research work; the 0.5 class is dropped.
FULL_WEIGHT = 1.0
LOW_WEIGHT = 0.0

WEIGHT_LEGEND = "edits/writes/mutating Bash = 1, reads/searches/inspection/MCP = 0"

# Workflow machinery that must never trip the brake — weight 0, no event.
DRIFT_EXEMPT_TOOL_NAMES = frozenset({
    'ToolSearch', 'AskUserQuestion', 'TodoWrite', 'Skill', 'SendMessage',
})

# Built-in mutating tools — full weight.
FULL_WEIGHT_TOOL_NAMES = frozenset({'Edit', 'Write', 'NotebookEdit', 'MultiEdit'})

# Serena (any server name containing 'serena') tool short-names.
SERENA_MEMORY_TOOLS = frozenset({
    'read_memory', 'list_memories', 'search_memories_by_name',
    'search_memories_by_front_matter', 'write_memory', 'edit_memory',
    'delete_memory', 'rename_memory',
})
SERENA_EDIT_TOOLS = frozenset({
    'replace_symbol_body', 'replace_content', 'insert_before_symbol',
    'insert_after_symbol', 'rename_symbol', 'safe_delete_symbol',
    'replace_in_files', 'create_text_file', 'replace_lines', 'delete_lines',
    'insert_at_line',
})

# At this streak, the advisory becomes a MANDATE (see core.stream for the
# shared constant the sibling edit gate also enforces against).
MANDATE_TEXT = (
    "STOP doing the work yourself. Split the remaining work and launch "
    "parallel subagents NOW (haiku=routine/recon/tests, sonnet=implementation "
    "— FEATURE_SUBAGENTS). For a genuinely tight single-file coupled fix, "
    "record a NEW 'single-agent: <reason>' line in the WM Context section to "
    "continue solo — a note written before this mandate does NOT count, and "
    "the override lasts only until the next background delegation; the edit "
    "gate blocks further edits otherwise."
)

DELEGATION_TOOL_NAMES = {'Agent', 'Task', 'Workflow'}

# Agent/Task calls launched in the foreground (run_in_background missing or
# False) block the orchestrator on one subagent — not the parallel-swarm
# hand-off this hook's reset is meant to reward.
FOREGROUND_CAPABLE_TOOL_NAMES = {'Agent', 'Task'}

# Bash commands whose PRIMARY (first pipeline-group) stage is verification —
# checking state or running tests/compiles — rather than doing task work.
BASH_GROUP_SPLIT_RE = re.compile(r'(?:;|&&|\|\||\n|(?<!\d>)&(?!\d))+')
BASH_PIPE_SPLIT_RE = re.compile(r'\|(?!\|)')
BASH_ENV_ASSIGN_RE = re.compile(
    r'^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S*)\s+)*')
BASH_VERIFICATION_FIRST_RE = re.compile(
    r'^(?:'
    r'git\s+(?:status|diff|log|show|commit|add)\b'
    r'|python3?\s+-m\s+(?:unittest|py_compile|pytest)\b'
    r'|pytest\b'
    r'|npm\s+(?:test|run\s+test)\b'
    r'|jq\s+\.'
    r'|(?:python3?\s+)?(?:scripts/)?validate-[\w.-]*\.py\b'
    r')',
    re.IGNORECASE,
)

# Read-only inspection commands (grep/cat/ls/etc) — checking state, same as
# the test-runner/validate patterns above, but these never execute code or
# mutate anything. Matched against the PRIMARY stage the same way.
BASH_INSPECTION_FIRST_RE = re.compile(
    r'^(?:'
    r'grep\b|rg\b|cat\b|head\b|tail\b|ls\b|wc\b|find\b'
    r'|sed\s+-n\b|awk\b|git\s+grep\b|file\b|stat\b|diff\b'
    r')',
    re.IGNORECASE,
)

# A command group containing any of these disqualifies the WHOLE call from
# verification exemption, even if the primary stage looks like inspection or
# a test runner — these are mutation/side-effect signals: output redirection
# (except stderr-to-null/stderr-to-stdout), in-place sed, find's -exec/
# -execdir/-delete, tee, xargs.
BASH_DISQUALIFIER_RE = re.compile(
    r'(?:^|\s)>>?(?!\s*/dev/null\b)(?!&1\b)'  # > or >> (not 2>/dev/null, 2>&1)
    r'|\bsed\s+-i\b'
    r'|-exec\b|-execdir\b|-delete\b'
    r'|\btee\b|\bxargs\b',
)


def bash_is_verification(command: str) -> bool:
    """True when EVERY command group in `command` is a verification/inspection
    call — the whole Bash call is checking state, not doing task work.

    A command group counts as verification when its primary (first pipeline)
    stage matches a known test-runner/build-check pattern
    (BASH_VERIFICATION_FIRST_RE), scope_guard's own test-command detector
    (is_test_command — playwright/jest/vitest/phpunit/go test/cargo test, the
    SAME classification scope_guard.classify_kind uses for its 'test' kind),
    OR a read-only inspection command (BASH_INSPECTION_FIRST_RE: grep, rg,
    cat, head, tail, ls, wc, find, sed -n, awk, git grep, file, stat, diff).

    A mixed group (e.g. `edit-ish-thing && git status`) still counts as task
    work: any non-verification group disqualifies the whole call. The call is
    ALSO disqualified outright (regardless of primary-stage match) when it
    contains output redirection, `sed -i`, `find -exec`/`-execdir`/`-delete`,
    `tee`, or `xargs` — these mutate state even when dressed up as a filter
    pipeline (e.g. `grep -l TODO *.py | xargs sed -i ...`).
    """
    if not command:
        return False
    if BASH_DISQUALIFIER_RE.search(command):
        return False
    groups = [g for g in BASH_GROUP_SPLIT_RE.split(command) if g.strip()]
    if not groups:
        return False
    for group in groups:
        first_stage = BASH_PIPE_SPLIT_RE.split(group, 1)[0].strip()
        first_stage = BASH_ENV_ASSIGN_RE.sub('', first_stage)
        if (BASH_VERIFICATION_FIRST_RE.match(first_stage)
                or is_test_command(first_stage)
                or BASH_INSPECTION_FIRST_RE.match(first_stage)):
            continue
        return False
    return True


def is_background_delegation(tool_name: str, tool_input: dict) -> bool:
    """True when this delegation-tool call is a real hand-off that should
    reset the drift counter.

    - Workflow: always a background hand-off — always resets.
    - Agent/Task: resets ONLY when tool_input['run_in_background'] is exactly
      True. Missing, False, or any other value means the orchestrator is
      blocking on a single foreground agent, which does not reset the streak
      (see module docstring).
    - Any other tool_name, or a non-dict/None tool_input for Agent/Task:
      False.
    """
    if tool_name == 'Workflow':
        return True
    if tool_name in FOREGROUND_CAPABLE_TOOL_NAMES:
        if not isinstance(tool_input, dict):
            return False
        return tool_input.get('run_in_background') is True
    return False


def drift_weight(tool_name: str, tool_input: dict) -> float:
    """Drift weight of one main-agent, non-delegation tool call.

    0.0 for workflow machinery (DRIFT_EXEMPT_TOOL_NAMES, Serena memory tools,
    swe-wm MCP tools); FULL_WEIGHT for built-in edits, Serena edit tools and
    mutating Bash; LOW_WEIGHT for verification/inspection Bash, every other
    MCP tool, and every other built-in (Read/Grep/Glob/WebFetch/…).
    """
    if tool_name in DRIFT_EXEMPT_TOOL_NAMES:
        return 0.0
    if tool_name in FULL_WEIGHT_TOOL_NAMES:
        return FULL_WEIGHT
    if tool_name == 'Bash':
        command = str((tool_input or {}).get('command', ''))
        return LOW_WEIGHT if bash_is_verification(command) else FULL_WEIGHT
    if tool_name.startswith('mcp__'):
        parts = tool_name.split('__')
        server = parts[1].lower() if len(parts) > 2 else ''
        short = parts[-1]
        if 'swe-wm' in server or 'swe_wm' in server:
            return 0.0
        if 'serena' in server:
            if short in SERENA_MEMORY_TOOLS:
                return 0.0
            if short in SERENA_EDIT_TOOLS:
                return FULL_WEIGHT
        return LOW_WEIGHT
    return LOW_WEIGHT


def is_task_work(tool_name: str, tool_input: dict) -> bool:
    """True when this tool call is FULL-weight task work (an edit, Serena
    edit, or mutating Bash) — see drift_weight for the full scale."""
    return drift_weight(tool_name, tool_input) >= FULL_WEIGHT


# ---------------------------------------------------------------------------
# Scope-guard event logging (agent_spawn / agent_ok / scope_extend)
# ---------------------------------------------------------------------------

# `agentId: <id>` (or `agent_id: <id>`) embedded in a stringified Agent-tool
# tool_response. The documented PostToolUse payload for the Agent tool gives
# tool_response as {"type": "text", "text": "<free-form result text>"} — no
# structured id field — so a background launch's confirmation text is parsed
# with this regex as the fallback path. A future harness version that adds a
# structured field is checked FIRST (see extract_spawned_agent_id) and this
# regex only runs when no such field is present.
_AGENT_ID_TEXT_RE = re.compile(
    r'\bagent[_-]?id\b\s*[:=]\s*["\']?([A-Za-z0-9._-]+)', re.IGNORECASE)


def extract_spawned_agent_id(tool_response) -> str:
    """Best-effort extraction of a newly spawned agent's id from an Agent/Task
    tool's PostToolUse `tool_response`.

    Checks structured shapes first (in case a harness version supplies them
    directly), then falls back to a regex over the stringified response for
    the documented free-form-text shape ({"type": "text", "text": "..."}) —
    a background launch's confirmation text names the spawned agent's id as
    `agentId: <id>`. Returns '' when no id can be found; callers then log no
    agent_spawn event at all (scope_guard.DEFAULT_BUDGET applies instead).
    """
    if isinstance(tool_response, dict):
        for key in ('agent_id', 'agentId'):
            val = tool_response.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        # Structured-but-textual shape: {"type": "text", "text": "..."}
        text = tool_response.get('text')
        if isinstance(text, str):
            match = _AGENT_ID_TEXT_RE.search(text)
            if match:
                return match.group(1)
        return ''
    if isinstance(tool_response, str):
        match = _AGENT_ID_TEXT_RE.search(tool_response)
        if match:
            return match.group(1)
        return ''
    return ''


def resolve_spawn_budget(tool_input: dict) -> int:
    """Resolve the tool-call budget for a newly spawned agent.

    A `[swe-budget: N]` tag in the spawning prompt (scope_guard.
    parse_budget_tag) overrides the model-family default
    (scope_guard.budget_for_model) computed from tool_input['model'].
    """
    tool_input = tool_input or {}
    tag_budget = parse_budget_tag(tool_input.get('prompt', ''))
    if tag_budget is not None:
        return tag_budget
    return budget_for_model(tool_input.get('model', ''))


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)

        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)
        if not session_id:
            output_empty()
            return

        tool_name = get_input_field(input_data, 'tool_name', default='')
        tool_input = get_input_field(input_data, 'tool_input', default={})
        stream_path = get_stream_path(session_id)

        # Subagents are not orchestrators — never track DRIFT for their own
        # tool calls (they are expected to do direct work). They DO still
        # get scope-guard credit here: PostToolUse only fires on success, so
        # a classify_kind()-recognized call (edit/test/bash) from a NAMED
        # spawned agent logs agent_ok, resetting that kind's failure streak
        # (core.scope_guard). A failed call never reaches this hook — it
        # routes to PostToolUseFailure, handled by swe_post_tool_failure.py.
        if is_spawned_agent(input_data) or is_subagent_transcript(transcript_path):
            agent_id = get_agent_id(input_data)
            kind = classify_kind(tool_name, tool_input)
            if agent_id and kind is not None:
                append_event(stream_path, 'agent_ok',
                             agent=agent_id, kind=kind, s=session_id)
            output_empty()
            return

        # Main-agent SendMessage: a [scope-extend] tag lifts a spawned
        # agent's scope-guard trip. SendMessage is neither task work nor a
        # delegation for DRIFT counting — it never touches the drift streak,
        # tagged or not.
        if tool_name == 'SendMessage':
            budget_add = parse_scope_extend(tool_input.get('message', ''))
            if budget_add is not None:
                target_agent = tool_input.get('to', '')
                if target_agent:
                    append_event(stream_path, 'scope_extend',
                                 agent=target_agent, budget_add=budget_add,
                                 s=session_id)
            output_empty()
            return

        # Main-agent Agent/Task call: this is where the agent actually
        # spawned, so its tool_response carries (in free-form text, per the
        # documented PostToolUse payload) the launched agent's id — logged
        # here as agent_spawn with its resolved budget. Runs BEFORE the
        # drift delegation/task-work accounting below, which is unaffected
        # by whether an id was extracted.
        if tool_name in ('Agent', 'Task'):
            tool_response = get_input_field(input_data, 'tool_response', default='')
            spawned_id = extract_spawned_agent_id(tool_response)
            if spawned_id:
                budget = resolve_spawn_budget(tool_input)
                spawn_fields = {
                    'agent': spawned_id,
                    'model': tool_input.get('model', ''),
                    'budget': budget,
                    's': session_id,
                }
                if expects_red_runs((tool_input or {}).get('prompt', '')):
                    spawn_fields['expect_red'] = True
                append_event(stream_path, 'agent_spawn', **spawn_fields)

        foreground_delegation = False
        if tool_name in DELEGATION_TOOL_NAMES:
            if is_background_delegation(tool_name, tool_input):
                append_event(stream_path, 'delegation', tool=tool_name, s=session_id)
                output_status("\U0001f501 delegation logged — drift counter reset")
                return
            # Foreground Agent/Task: not a reset — falls through to the
            # ordinary task_work path below.
            foreground_delegation = True

        weight = FULL_WEIGHT if foreground_delegation else drift_weight(tool_name, tool_input)
        if weight <= 0:
            output_empty()
            return

        append_event(stream_path, 'task_work', tool=tool_name, w=weight, s=session_id)
        drift_count = count_task_work_since_delegation(stream_path)
        shown = format_drift_weight(drift_count)

        if drift_count >= DRIFT_HARD_THRESHOLD:
            # Snapshot pre-existing single-agent notes NOW so only a note
            # written after this mandate disarms the edit gate.
            wm_content = ''
            cwd = get_input_field(input_data, 'cwd', default='') or os.getcwd()
            wm_path = find_working_memory_for_session(cwd, session_id)
            if wm_path:
                try:
                    with open(wm_path, 'r') as f:
                        wm_content = f.read()
                except IOError:
                    wm_content = ''
            record_drift_hard_block(stream_path, wm_content, session_id)
            output = HookOutput(event_name="PostToolUse")
            message = (
                f"Orchestrator drift: weighted task-work {shown} without "
                f"delegating (>= hard threshold {DRIFT_HARD_THRESHOLD}; "
                f"{WEIGHT_LEGEND}). " + MANDATE_TEXT
            )
            if foreground_delegation:
                message = (
                    f"FOREGROUND delegation ({tool_name}) does not reset drift — "
                    "it blocks the orchestrator on one subagent instead of "
                    "parallel-splitting. Relaunch with run_in_background: true. "
                ) + message
            output.add_message(message)
            output.output_and_exit()
            return

        if drift_count >= DRIFT_THRESHOLD:
            # A direct, literally-targeted instruction this turn (the prompt
            # hook's fast path, swe_user_prompt_workflow.is_direct_instruction)
            # is not orchestrator drift — the user named the target, so
            # applying it directly IS the correct behavior, not a sign the
            # model should have delegated. Suppress the advisory ONLY below
            # the hard threshold; HARD-threshold behavior (deny + mandate)
            # stays unconditional regardless of a direct instruction.
            if has_event_since_last(stream_path, 'direct_instruction', marker_type='prompt'):
                output_status(f"\U0001f6e0️ weighted task-work {shown} since last delegation "
                              "(direct instruction this turn — advisory suppressed)")
                return
            output = HookOutput(event_name="PostToolUse")
            message = (
                f"Orchestrator drift: weighted task-work {shown} without "
                f"delegating (advisory threshold {DRIFT_THRESHOLD}; {WEIGHT_LEGEND}) "
                "— split remaining work into parallel background subagents "
                "(see FEATURE_SUBAGENTS)."
            )
            if foreground_delegation:
                message = (
                    f"FOREGROUND delegation ({tool_name}) does not reset drift — "
                    "it blocks the orchestrator on one subagent instead of "
                    "parallel-splitting. Relaunch with run_in_background: true. "
                ) + message
            output.add_message(message)
            output.output_and_exit()
            return

        if foreground_delegation:
            output_status(
                f"\U0001f6e0️ weighted task-work {shown} since last delegation "
                f"(FOREGROUND {tool_name} does not reset drift — relaunch with "
                "run_in_background: true to hand off for real)"
            )
        else:
            output_status(f"\U0001f6e0️ weighted task-work {shown} (+{format_drift_weight(weight)} "
                          f"{tool_name}) since last delegation")

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                         "additionalContext": f"Orchestrator-drift hook error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
