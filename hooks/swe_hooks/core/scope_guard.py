"""Per-subagent scope guard: tool-call budget + failure-streak circuit breaker.

Problem: a delegated subagent given a simple task can hit an unrelated issue
and keep debugging far outside its assigned scope — burning tool calls on
increasingly desperate attempts instead of reporting back to the
orchestrator. This module gives every spawned agent (identified by
core.session.get_agent_id) a bounded budget of tool calls plus a
per-tool-kind consecutive-failure streak limit, both scoped to THAT agent's
own events in the session stream (never the main agent's or a sibling
subagent's — the same per-agent partitioning
core.stream.collect_values_since_task_start already uses for docread
credit).

Event vocabulary (appended to the session JSONL stream, see core.stream):
  agent_spawn  {agent, model, budget}   — logged when an Agent/Task call
                                           spawns a NAMED subagent (Stage 2
                                           wiring, not done by this module).
  agent_call   {agent, tool}            — one tool call by that agent,
                                           logged by the init gate.
  agent_ok     {agent, kind}            — a call of `kind` ('edit'/'test'/
                                           'bash') succeeded, resets that
                                           kind's failure streak.
  agent_fail   {agent, kind}            — a call of `kind` failed, extends
                                           that kind's failure streak.
  scope_extend {agent, budget_add}      — the orchestrator lifted the trip
                                           (via a SendMessage carrying
                                           [scope-extend]): adds budget_add
                                           to the budget and resets every
                                           failure streak.

Budget resolution: a model's DEFAULT per-spawn budget (MODEL_BUDGETS, keyed
by family — "any model string containing 'haiku'/'sonnet'/'opus'/'fable'")
may be overridden per-call by a `[swe-budget: N]` tag in the spawning
prompt (parse_budget_tag) — Stage 2 wiring reads that tag when it logs
agent_spawn. This module only computes the resulting numbers from whatever
was logged; it does not itself read prompts at spawn time (that is the
Agent/Task-side integration, not the per-tool-call gate this module backs).

Everything below is a pure function over money already collected by the
gate (session stream events) — no I/O beyond reading the stream file itself
(load_agent_events). stdlib only.
"""

import json
import os
import re
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Consecutive same-kind failures that trip the scope gate for that kind.
FAIL_STREAK_LIMIT = {'test': 2, 'edit': 2, 'bash': 3}

# Default per-spawn tool-call budget, by model family. A model string is
# matched by substring containment (case-insensitive) against each key, so
# both short aliases ("haiku") and full model ids ("claude-haiku-5-1") match.
MODEL_BUDGETS = {'haiku': 25, 'sonnet': 60, 'opus': 120, 'fable': 120}

# Fallback budget for an unrecognized/missing model family.
DEFAULT_BUDGET = 60

# Default budget added by a bare `[scope-extend]` tag (no explicit N).
DEFAULT_EXTEND = 30

# `[swe-budget: N]` — overrides the model-family default at spawn time.
BUDGET_TAG_RE = re.compile(r'\[swe-budget\s*:\s*(\d+)\]', re.IGNORECASE)

# `[scope-extend]` or `[scope-extend: N]` — the orchestrator lifting a trip.
SCOPE_EXTEND_RE = re.compile(r'\[scope-extend(?:\s*:\s*(\d+))?\]', re.IGNORECASE)

# Edit-class tools: Edit/Write/NotebookEdit plus the Serena content-mutation
# tools (both the "mcp__plugin_swe_serena__" and legacy "mcp__serena__"
# prefixes) — the SAME tool set hooks/hooks.json's own PreToolUse matchers
# use for edit-adjacent gates (swe_pre_edit_validate, doc-index gate), kept
# here as the single Python-side source of truth rather than re-deriving it.
EDIT_TOOLS = frozenset([
    'Edit', 'Write', 'NotebookEdit',
    'mcp__plugin_swe_serena__replace_symbol_body',
    'mcp__plugin_swe_serena__replace_content',
    'mcp__plugin_swe_serena__replace_in_files',
    'mcp__plugin_swe_serena__insert_before_symbol',
    'mcp__plugin_swe_serena__insert_after_symbol',
    'mcp__plugin_swe_serena__rename_symbol',
    'mcp__plugin_swe_serena__safe_delete_symbol',
    'mcp__serena__replace_symbol_body',
    'mcp__serena__replace_content',
    'mcp__serena__replace_in_files',
    'mcp__serena__insert_before_symbol',
    'mcp__serena__insert_after_symbol',
    'mcp__serena__rename_symbol',
    'mcp__serena__safe_delete_symbol',
])

# Tools that remain available to a tripped agent — read-only investigation
# and the means to report back / stop, never further mutation or execution.
READ_ONLY_TOOLS = frozenset([
    'Read', 'Grep', 'Glob', 'LS', 'ToolSearch', 'SendMessage', 'TaskStop',
    'mcp__plugin_swe_serena__read_memory',
    'mcp__plugin_swe_serena__list_memories',
    'mcp__plugin_swe_serena__search_memories_by_name',
    'mcp__plugin_swe_serena__search_memories_by_front_matter',
    'mcp__plugin_swe_serena__find_symbol',
    'mcp__plugin_swe_serena__get_symbols_overview',
    'mcp__plugin_swe_serena__find_referencing_symbols',
    'mcp__plugin_swe_serena__find_declaration',
    'mcp__plugin_swe_serena__find_implementations',
    'mcp__plugin_swe_serena__search_for_pattern',
    'mcp__plugin_swe_serena__get_diagnostics_for_file',
    'mcp__serena__read_memory',
    'mcp__serena__list_memories',
    'mcp__serena__search_memories_by_name',
    'mcp__serena__search_memories_by_front_matter',
    'mcp__serena__find_symbol',
    'mcp__serena__get_symbols_overview',
    'mcp__serena__find_referencing_symbols',
    'mcp__serena__find_declaration',
    'mcp__serena__find_implementations',
    'mcp__serena__search_for_pattern',
    'mcp__serena__get_diagnostics_for_file',
    'mcp__plugin_swe_swe-wm__swe_wm_read',
])


# ---------------------------------------------------------------------------
# Test-command detection
# ---------------------------------------------------------------------------
# SINGLE SOURCE OF TRUTH for test-runner command classification, used by
# THIS module's classify_kind (the 'test' kind) and imported by
# hooks/pre/swe_pre_bash_test_gate.py for its own test-command gate. This
# module is pure/side-effect-free (stdlib only, no swe_hooks.bootstrap
# import), so the PreToolUse hook — whose own top-level import chain is
# heavier — imports FROM here rather than the reverse.
TEST_COMMAND_PATTERNS = [
    r'\bnpx\s+playwright\s+test\b',
    r'\bpython3?\s+-m\s+(?:unittest|pytest)\b',
    r'(?<!\w)pytest\b',
    r'\bnpm\s+(?:run\s+)?test\b',
    r'\bnpx\s+(?:jest|vitest|playwright\s+test)\b',
    r'(?:^|[/\s])(?:vendor/bin/)?phpunit\b',
    r'\bgo\s+test\b',
    r'\bcargo\s+test\b',
]


def _is_test_command(command: str) -> bool:
    """True when `command` matches one of TEST_COMMAND_PATTERNS."""
    command = command or ''
    for pattern in TEST_COMMAND_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------

def budget_for_model(model: str) -> int:
    """Default tool-call budget for `model`, by family (substring match).

    Checks 'haiku'/'sonnet'/'opus'/'fable' as lowercase substrings of `model`
    (covers both short aliases and full model ids, e.g. "claude-haiku-5-1").
    Falls back to DEFAULT_BUDGET when no family matches or `model` is empty.
    """
    m = (model or '').strip().lower()
    for family in ('haiku', 'sonnet', 'opus', 'fable'):
        if family in m:
            return MODEL_BUDGETS[family]
    return DEFAULT_BUDGET


def parse_budget_tag(prompt: str) -> Optional[int]:
    """Parse a `[swe-budget: N]` tag out of `prompt`, or None if absent."""
    if not prompt:
        return None
    match = BUDGET_TAG_RE.search(prompt)
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_scope_extend(message: str) -> Optional[int]:
    """Parse a `[scope-extend]` / `[scope-extend: N]` tag out of `message`.

    Returns None when no tag is present, DEFAULT_EXTEND for a bare tag (no
    explicit N), or the parsed N otherwise.
    """
    if not message:
        return None
    match = SCOPE_EXTEND_RE.search(message)
    if not match:
        return None
    n = match.group(1)
    if n is None:
        return DEFAULT_EXTEND
    try:
        return int(n)
    except (TypeError, ValueError):
        return DEFAULT_EXTEND


def classify_kind(tool_name: str, tool_input: dict) -> Optional[str]:
    """Classify a tool call into a scope-guard 'kind', or None if untracked.

    'edit'  — tool_name is in EDIT_TOOLS.
    'test'  — tool_name == 'Bash' and its command matches a test-runner
              pattern (TEST_COMMAND_PATTERNS).
    'bash'  — tool_name == 'Bash' and it is NOT a test command.
    None    — everything else (including READ_ONLY_TOOLS — those are never
              streak-tracked, only budget-counted like any other call).
    """
    if tool_name in EDIT_TOOLS:
        return 'edit'
    if tool_name == 'Bash':
        command = str((tool_input or {}).get('command', ''))
        return 'test' if _is_test_command(command) else 'bash'
    return None


def load_agent_events(stream_path: str, agent_id: str) -> list:
    """Read `stream_path` (a session JSONL stream) and return every event
    belonging to `agent_id` whose type is one this module tracks:
    agent_spawn, agent_call, agent_ok, agent_fail, scope_extend.

    Full-file read — per-session streams are small (matches the read
    strategy every other core.stream reader uses for non-tail-optimized
    scans). Missing file or unreadable lines are tolerated: returns whatever
    could be parsed (possibly an empty list), never raises.
    """
    tracked_types = {'agent_spawn', 'agent_call', 'agent_ok', 'agent_fail',
                      'scope_extend'}
    events = []
    if not stream_path or not os.path.exists(stream_path):
        return events
    try:
        with open(stream_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except IOError:
        return events
    for line in lines:
        try:
            event = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') not in tracked_types:
            continue
        if event.get('agent') != agent_id:
            continue
        events.append(event)
    return events


def scope_state(events: list, agent_id: str) -> dict:
    """Fold `events` (already filtered to `agent_id`, in stream order) into
    the agent's current scope state:

        {budget: int, calls: int, streaks: {kind: int}, extended: int}

    budget   = the latest agent_spawn's `budget` for this agent (else
               DEFAULT_BUDGET) + the sum of every scope_extend's budget_add.
    calls    = count of agent_call events.
    streaks  = per-kind consecutive-failure count: an agent_fail for `kind`
               increments streaks[kind]; an agent_ok for the SAME kind resets
               it to 0. A scope_extend resets EVERY kind's streak to 0
               (the orchestrator lifting the trip clears all outstanding
               failure history, not just the kind that tripped it).
    extended = total budget added by scope_extend events (informational).
    """
    spawn_budget = DEFAULT_BUDGET
    extended = 0
    calls = 0
    streaks = {}

    for event in events or []:
        if event.get('agent') != agent_id:
            continue
        etype = event.get('type')
        if etype == 'agent_spawn':
            b = event.get('budget')
            if isinstance(b, (int, float)):
                spawn_budget = int(b)
        elif etype == 'agent_call':
            calls += 1
        elif etype == 'agent_ok':
            kind = event.get('kind')
            if kind:
                streaks[kind] = 0
        elif etype == 'agent_fail':
            kind = event.get('kind')
            if kind:
                streaks[kind] = streaks.get(kind, 0) + 1
        elif etype == 'scope_extend':
            add = event.get('budget_add')
            if isinstance(add, (int, float)):
                extended += int(add)
            streaks = {k: 0 for k in streaks}

    return {
        'budget': spawn_budget + extended,
        'calls': calls,
        'streaks': streaks,
        'extended': extended,
    }


def _budget_exhausted_message(calls: int, budget: int) -> str:
    return (
        f"[scope-gate] tool-call budget exhausted ({calls}/{budget}). "
        "STOP. Do not keep debugging. Report to the orchestrator now: what "
        "failed, exact evidence (commands + output), your hypothesis, and "
        "what you did NOT try. Only read-only tools remain available. The "
        "orchestrator can lift this with a SendMessage containing "
        "[scope-extend]."
    )


def _fail_streak_message(kind: str, count: int) -> str:
    return (
        f"[scope-gate] {kind} failed {count} times in a row. "
        "STOP. Do not keep debugging. Report to the orchestrator now: what "
        "failed, exact evidence (commands + output), your hypothesis, and "
        "what you did NOT try. Only read-only tools remain available. The "
        "orchestrator can lift this with a SendMessage containing "
        "[scope-extend]."
    )


def scope_verdict(state: dict, tool_name: str) -> str:
    """Deny message when `tool_name` should be blocked under `state`, else
    '' (empty string means allow).

    Read-only tools (READ_ONLY_TOOLS) are ALWAYS allowed, regardless of
    budget or streak state — an agent that has tripped the gate must still
    be able to investigate, report, and stop. Otherwise: budget exhaustion
    (calls >= budget) denies first; a per-kind failure streak at or past
    FAIL_STREAK_LIMIT denies next. Empty state / unknown tool never denies.
    """
    if tool_name in READ_ONLY_TOOLS:
        return ''

    budget = state.get('budget', DEFAULT_BUDGET)
    calls = state.get('calls', 0)
    if calls >= budget:
        return _budget_exhausted_message(calls, budget)

    streaks = state.get('streaks') or {}
    for kind, limit in FAIL_STREAK_LIMIT.items():
        if streaks.get(kind, 0) >= limit:
            return _fail_streak_message(kind, streaks[kind])

    return ''
