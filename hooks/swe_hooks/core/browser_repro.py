"""Browser-repro-first gate: pure detection helpers.

Problem (incident 2026-10-02): an E2E (Playwright) spec failed; the
orchestrator then spent 4+ rerun cycles delegating "rerun the spec with fix
X" agents on unverified theories, never reproducing the failing step in the
browser-devtools MCP — the documented first move (browser = source of
truth, see mem:feedback/FEEDBACK_TDD_FOR_BUG_FIXES "browser-repro section").

Rule this module backs: once an E2E run FAILS, no further E2E run and no
spec-rerun/debug DELEGATION is allowed until the failing flow has been
reproduced in mcp__browser-devtools__* — i.e. a 'browser_repro' stream event
must be appended AFTER the most recent 'e2e_fail' event.

Everything here is a pure function over strings/event-lists — no I/O. Stdlib
only, mirrors core.scope_guard's shape (the module hooks/pre/*.py and
hooks/post/*.py import pure helpers FROM).
"""

import re
from typing import Optional


# ---------------------------------------------------------------------------
# E2E command detection
# ---------------------------------------------------------------------------
# The last two patterns are the Convenely plugin-repo Playwright runners
# (convenely_plugin_repo/tests/package.json): `npm run demo1:t -- "..."`
# (single test on demo1) and `npm run demo1[:<project>]` (all/one project on
# demo1) — both ultimately invoke `npx playwright test` under the hood, but
# the npm-script form never contains that literal substring, so it needs its
# own pattern alongside the direct playwright-test and run-test-single.sh
# forms.
E2E_COMMAND_PATTERNS = [
    r'\bnpx\s+playwright\s+test\b',
    r'run-test-single\.sh',
    r'\bnpm\s+run\s+[\w-]+:t\b',
    r'\bnpm\s+run\s+demo1(?::[\w-]+)?\b',
]

_E2E_COMMAND_RE = [re.compile(p, re.IGNORECASE) for p in E2E_COMMAND_PATTERNS]


def is_e2e_command(command: str) -> bool:
    """True when `command` invokes an E2E (Playwright) test runner.

    Matches anywhere in a multi-line/compound command string (DOTALL is not
    needed — re.search already scans the whole string, including a gated
    command hidden on a later line of a multi-line Bash call).
    """
    if not command:
        return False
    return any(p.search(command) for p in _E2E_COMMAND_RE)


# ---------------------------------------------------------------------------
# Failed E2E output detection
# ---------------------------------------------------------------------------
# A Playwright run redirected to a log file (`... > run.log 2>&1; echo exit $?`)
# succeeds at the SHELL level even when the spec itself failed — the shell's
# own exit code reflects the `echo`, not playwright. Detection must therefore
# also read the captured text for Playwright's own failure markers.
_PLAYWRIGHT_FAILED_RE = re.compile(r'\b\d+\s+failed\b', re.IGNORECASE)
_EXIT_NONZERO_RE = re.compile(r'\bexit\s+([1-9]\d*)\b', re.IGNORECASE)


def is_failed_e2e_output(text: str) -> bool:
    """True when `text` (captured stdout/stderr of an E2E run) shows a
    Playwright failure: a "N failed" summary line, or an `exit N` marker
    (N != 0) — the pattern a redirected `... ; echo exit $?` run leaves
    behind when the shell's own exit code would otherwise read as success.
    """
    if not text:
        return False
    if _PLAYWRIGHT_FAILED_RE.search(text):
        return True
    return bool(_EXIT_NONZERO_RE.search(text))


# ---------------------------------------------------------------------------
# Browser-devtools tool detection
# ---------------------------------------------------------------------------
# Interaction/navigation/inspection tools under mcp__browser-devtools__* —
# NOT scenario-list/-search/-add/-delete/-update (those manage the scenario
# catalog, they are never themselves a repro step). scenario-run DOES count
# (it drives the browser through the real steps), as does execute (batches
# real browser actions in one call).
_BROWSER_DEVTOOLS_PREFIX = 'mcp__browser-devtools__'

_BROWSER_REPRO_PREFIXES = (
    'navigation_', 'interaction_', 'a11y_', 'content_', 'o11y_', 'debug_',
    'sync_', 'stub_', 'react_', 'browser_',
)

_BROWSER_REPRO_EXACT_SUFFIXES = frozenset(['scenario-run', 'execute'])

_BROWSER_CATALOG_EXACT_SUFFIXES = frozenset(
    ['scenario-list', 'scenario-search', 'scenario-add', 'scenario-delete',
     'scenario-update'])


def is_browser_repro_tool(tool_name: str) -> bool:
    """True for an mcp__browser-devtools__* tool that constitutes an actual
    browser-repro STEP (navigation, interaction, inspection, scenario-run,
    execute) — False for the scenario-CATALOG management tools
    (scenario-list/-search/-add/-delete/-update) and for anything outside the
    browser-devtools server.
    """
    name = str(tool_name or '')
    if not name.startswith(_BROWSER_DEVTOOLS_PREFIX):
        return False
    suffix = name[len(_BROWSER_DEVTOOLS_PREFIX):]
    if suffix in _BROWSER_CATALOG_EXACT_SUFFIXES:
        return False
    if suffix in _BROWSER_REPRO_EXACT_SUFFIXES:
        return True
    return suffix.startswith(_BROWSER_REPRO_PREFIXES)


# ---------------------------------------------------------------------------
# Ordering check: needs_browser_repro
# ---------------------------------------------------------------------------

def needs_browser_repro(events: list) -> bool:
    """True iff the last 'e2e_fail' event in `events` is AFTER the last
    'browser_repro' event (any 'agent' field — main agent or any spawned
    agent's repro both satisfy the requirement for the whole session).

    No 'e2e_fail' at all -> False (nothing has failed yet).
    An 'e2e_fail' with no 'browser_repro' at all -> True.
    `events` is assumed to be in chronological (append) order, the same
    order core.stream readers yield — the index of the LAST matching event
    of each type is what matters, not counts.
    """
    last_fail_idx: Optional[int] = None
    last_repro_idx: Optional[int] = None
    for i, event in enumerate(events or []):
        etype = event.get('type') if isinstance(event, dict) else None
        if etype == 'e2e_fail':
            last_fail_idx = i
        elif etype == 'browser_repro':
            last_repro_idx = i
    if last_fail_idx is None:
        return False
    if last_repro_idx is None:
        return True
    return last_fail_idx > last_repro_idx


# ---------------------------------------------------------------------------
# Delegation prompt detection
# ---------------------------------------------------------------------------
# Prompts that ask a spawned agent to rerun/debug an E2E spec — the exact
# shape of the 2026-10-02 incident's "rerun the spec with fix X" delegations.
DELEGATION_PATTERNS = [
    r'playwright',
    r'\.spec\.ts\b',
    r'run-test-single',
    r'demo1:t\b',
    r'\bnpm\s+run\s+demo1\b',
]

_DELEGATION_RE = [re.compile(p, re.IGNORECASE) for p in DELEGATION_PATTERNS]


def is_e2e_delegation(prompt: str) -> bool:
    """True when an Agent/Task `prompt` reads as a request to rerun or debug
    an E2E (Playwright) spec — any of DELEGATION_PATTERNS appearing anywhere
    in the prompt text."""
    if not prompt:
        return False
    return any(p.search(prompt) for p in _DELEGATION_RE)


# ---------------------------------------------------------------------------
# Escape hatch
# ---------------------------------------------------------------------------
# Asserts the failure is NOT browser-reproducible (a pure REST/CLI spec with
# no UI flow) — honored only when literally present in the command string,
# same shape as other escape prefixes in this project (PUSH_APPROVED=1, etc).
BROWSER_REPRO_NA_RE = re.compile(r'\bBROWSER_REPRO_NA\s*=\s*1\b')


def has_browser_repro_na(command: str) -> bool:
    """True when `command` carries the BROWSER_REPRO_NA=1 escape prefix."""
    if not command:
        return False
    return bool(BROWSER_REPRO_NA_RE.search(command))
