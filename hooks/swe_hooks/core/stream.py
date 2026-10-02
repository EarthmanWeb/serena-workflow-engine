"""Stream-based event tracking. Append-only JSONL.

All hooks import this module to append events.
No separate hook process needed - piggybacks on existing hooks.

Events: {t: epoch, type: "tool|state|edit|checkpoint|interrupted", ...}
"""
import os
import json
import re
import time
from typing import Optional


def get_stream_dir() -> str:
    """Get stream directory, creating if needed."""
    try:
        from swe_hooks.core.config import get_project_root
        project_dir = get_project_root()
    except ImportError:
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
    stream_dir = os.path.join(project_dir, '.serena', 'streams')
    os.makedirs(stream_dir, exist_ok=True)
    return stream_dir


def get_stream_path(session_id: str) -> str:
    """Get stream file path for a session."""
    return os.path.join(get_stream_dir(), f'{session_id}.jsonl')


def get_sentinel_path(session_id: str) -> str:
    """Get sentinel file path for init gate cache."""
    return os.path.join(get_stream_dir(), f'.init_{session_id}')


def get_feature_sentinel_path(session_id: str, gate_name: str) -> str:
    """Get sentinel file path for a feature/task gate.

    Pattern: .serena/streams/.{gate_name}_feature_{session_id}
    Gates: 'test' (FEATURE_TESTS read), 'sweep' (WF_CLASSIFY 4d sweep verified).
    """
    return os.path.join(get_stream_dir(), f'.{gate_name}_feature_{session_id}')


def get_edit_mode_path(session_id: str) -> str:
    """Sentinel path for the session's edit-mode flag.

    Pattern: .serena/streams/.edit_mode_{session_id} — same family as
    get_sentinel_path (init) / get_feature_sentinel_path (test/sweep gates).
    Presence of the file = edit mode ON; absence = OFF. Content is a small
    JSON blob (set_at epoch) for debuggability, never parsed for the flag
    itself — existence is the signal, same as the init sentinel.
    """
    return os.path.join(get_stream_dir(), f'.edit_mode_{session_id}')


def is_edit_mode(session_id: str) -> bool:
    """True when the edit-mode sentinel exists for `session_id`."""
    if not session_id:
        return False
    return os.path.exists(get_edit_mode_path(session_id))


def set_edit_mode(session_id: str, on: bool) -> bool:
    """Turn the session's edit-mode flag on or off. Returns True on success.

    on=True writes the sentinel (best-effort, mirrors append_event's
    IOError swallow). on=False removes it if present; missing-file is not
    an error.
    """
    if not session_id:
        return False
    path = get_edit_mode_path(session_id)
    try:
        if on:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump({"session_id": session_id, "set_at": int(time.time())},
                          f, separators=(',', ':'))
        else:
            if os.path.exists(path):
                os.remove(path)
        return True
    except IOError:
        return False


def append_event(stream_path: str, event_type: str, **data):
    """Append an event to the stream. O(1) append, no reads."""
    event = {"t": int(time.time()), "type": event_type}
    event.update(data)
    try:
        os.makedirs(os.path.dirname(stream_path), exist_ok=True)
        with open(stream_path, 'a') as f:
            f.write(json.dumps(event, separators=(',', ':')) + '\n')
    except IOError:
        pass  # Best-effort, never block on stream failure


def count_events_since_last(stream_path: str, marker_types=('state', 'checkpoint'),
                             count_type: str = 'edit') -> int:
    """Count events of count_type since last marker event.

    Reads from END of file efficiently using seek.
    Falls back to full scan if file is small (<10KB).
    """
    if not os.path.exists(stream_path):
        return 0
    try:
        file_size = os.path.getsize(stream_path)
        with open(stream_path, 'r') as f:
            if file_size > 10240:
                # Large file: read last 10KB (~100 events)
                f.seek(max(0, file_size - 10240))
                f.readline()  # Skip partial first line
            lines = f.readlines()

        count = 0
        for line in reversed(lines):
            try:
                event = json.loads(line.strip())
                if event.get('type') in marker_types:
                    break
                if event.get('type') == count_type:
                    count += 1
            except (json.JSONDecodeError, ValueError):
                continue
        return count
    except IOError:
        return 0


def get_event_count(stream_path: str) -> int:
    """Get total event count efficiently (for periodic injection)."""
    if not os.path.exists(stream_path):
        return 0
    try:
        with open(stream_path, 'rb') as f:
            return sum(1 for _ in f)
    except IOError:
        return 0


def events_since_task_start(stream_path: str, since_sweep: bool = False) -> list:
    """All events since the current task started, in order.

    Task start = the LAST 'state' event whose to_s is WF_CLASSIFY (a follow-up
    task re-entering classification), or the last 'session_start' event if no
    such re-entry exists. Events from a prior task NEVER count toward the
    current task. Full-file scan — per-session streams are small.

    since_sweep=True ALSO treats the last successful 'sweep' marker as a
    boundary (whichever is latest wins). Once a sweep has passed, its docpending
    accounting is settled — a later sweep only reckons with links surfaced
    AFTER it, so prior work's already-cleared links never re-block a new,
    unrelated sweep in the same session (the cross-task accumulation bug).
    """
    if not os.path.exists(stream_path):
        return []
    try:
        with open(stream_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        return []

    events = []
    for line in lines:
        try:
            events.append(json.loads(line.strip()))
        except (json.JSONDecodeError, ValueError):
            continue

    start = 0
    for i, event in enumerate(events):
        etype = event.get('type')
        if etype == 'session_start':
            start = i
        elif etype == 'state' and event.get('to_s') == 'WF_CLASSIFY':
            start = i
        elif since_sweep and etype == 'sweep':
            start = i
    return events[start:]


def append_task_boundary(stream_path: str, from_state: str, session_id: str):
    """Stamp a task boundary: a 'state' event into WF_CLASSIFY.

    events_since_task_start() keys its boundary on exactly this shape, so it
    must be emitted ONLY at genuine new-task starts (prompt-hook new_task /
    same-session re-entry after WF_DONE) — NEVER for continuation, unclear,
    or slash-command prompts, which would drop the task's docreads and make
    sweep verification reject memories the agent already read this task.
    """
    append_event(stream_path, 'state',
                 from_s=from_state, to_s='WF_CLASSIFY', s=session_id)


def collect_values_since_task_start(stream_path: str, count_type: str = 'docread',
                                    value_key: str = 'name',
                                    since_sweep: bool = False,
                                    agent_id: Optional[str] = None) -> set:
    """Collect normalized value_key values from count_type events since the
    current task started. A list-valued key contributes every element.

    Values are normalized lowercase with any '.md' suffix and 'mem:' prefix
    stripped; malformed/truncated names are dropped (see is_valid_memory_name).

    since_sweep=True narrows the window to after the last successful sweep as
    well as the task boundary (used for docpending accounting).

    agent_id partitions events by WHO produced them (per-subagent docread
    tracking, core.session.get_agent_id): when given, only events whose
    'agent' field equals agent_id are counted; when None (default), only
    events WITHOUT an 'agent' field are counted — i.e. main-agent events.
    Pre-existing events carry no 'agent' field at all, so the default
    (agent_id=None) preserves prior main-agent-only behavior unchanged; every
    current caller omits agent_id and keeps seeing exactly what it always saw.
    """
    values = set()
    for event in events_since_task_start(stream_path, since_sweep=since_sweep):
        if event.get('type') != count_type:
            continue
        event_agent = event.get('agent')
        if agent_id is None:
            if event_agent:
                continue
        elif event_agent != agent_id:
            continue
        value = event.get(value_key)
        items = value if isinstance(value, list) else [value]
        for v in items:
            if not v:
                continue
            name = normalize_memory_name(str(v))
            if is_valid_memory_name(name):
                values.add(name)
    return values


def collect_values_session(stream_path: str, count_type: str = 'docread',
                            value_key: str = 'name',
                            agent_id: Optional[str] = None) -> set:
    """Collect normalized value_key values from count_type events across the
    WHOLE session stream file — no task-boundary window, unlike
    collect_values_since_task_start.

    Used by the edit doc-gate (swe_pre_edit_validate.py), per operator
    decision: dev-standards/doc reads count PER SESSION, not per task — a
    memory read earlier in the session (an earlier task, a prior prompt)
    still satisfies the doc-gate for a later task's edit, so the same
    FEATURE_*/DEV_* memory is never demanded twice in one session.

    agent_id has the SAME partitioning semantics as
    collect_values_since_task_start: None (default) counts only events with
    no 'agent' field (main-agent events); a given id counts only that
    agent's own events. Full-file scan — per-session streams are small (same
    cost profile as events_since_task_start).
    """
    if not os.path.exists(stream_path):
        return set()
    try:
        with open(stream_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        return set()

    values = set()
    for line in lines:
        try:
            event = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if event.get('type') != count_type:
            continue
        event_agent = event.get('agent')
        if agent_id is None:
            if event_agent:
                continue
        elif event_agent != agent_id:
            continue
        value = event.get(value_key)
        items = value if isinstance(value, list) else [value]
        for v in items:
            if not v:
                continue
            name = normalize_memory_name(str(v))
            if is_valid_memory_name(name):
                values.add(name)
    return values


def collect_docpending_sources(stream_path: str, since_sweep: bool = False) -> dict:
    """Map each docpending link surfaced this task → the set of source memories
    (`src`) that surfaced it.

    Used by the sweep gate's read-gated deferral rule: a pending link is
    deferrable ONLY when NONE of its sources is the current primary feature —
    i.e. it was raised by a paused/sibling-feature read during a task pivot, not
    by the feature the task is actually working on. Links whose event carries no
    `src` (pre-upgrade events) map to an empty source set and are treated as
    deferrable (fail-open on legacy data, never fail-closed on an un-taggable
    link).

    since_sweep matches the docpending accounting window (after the last
    successful sweep). Malformed/truncated link tokens are dropped.
    """
    sources = {}
    for event in events_since_task_start(stream_path, since_sweep=since_sweep):
        if event.get('type') != 'docpending':
            continue
        src = event.get('src')
        src = normalize_memory_name(str(src)) if src else None
        for link in event.get('new') or []:
            key = normalize_memory_name(str(link))
            if not is_valid_memory_name(key):
                continue
            bucket = sources.setdefault(key, set())
            if src:
                bucket.add(src)
    return sources


def normalize_memory_name(name: str) -> str:
    """Normalize a memory name for comparison: lowercase, strip whitespace,
    'mem:' prefix, and '.md' suffix."""
    name = name.strip().lower()
    if name.startswith('mem:'):
        name = name[4:]
    if name.endswith('.md'):
        name = name[:-3]
    return name


# ---------------------------------------------------------------------------
# Sweep/size-audit topic exclusions (single source of truth)
# ---------------------------------------------------------------------------
# USER DECISION (2026-09): spec/, report/, research/, and project/ are FULLY
# excluded from the WF_CLASSIFY Feature Knowledge Sweep AND from memory-size
# advisories — never demanded, never bulk-loaded, never needing a
# disposition, never withholding docs-first credit. A memory under one of
# these topics loads ONLY when the task explicitly names it.
#
# This is the ONE definition of the exclusion rule. Every other module
# (hooks/post/swe_post_read_state.py, hooks/swe_hooks/mcp/wm_server.py,
# hooks/swe_hooks/core/memory_size.py — and anything scripts/memory_size.py
# feeds) imports EXCLUDED_TOPICS / is_excluded_memory from here rather than
# keeping its own copy.
EXCLUDED_TOPICS = ("spec", "report", "research", "project")

# Basename prefixes for excluded topics, derived from EXCLUDED_TOPICS (e.g.
# "spec" -> "SPEC_"). Covers a bare "SPEC_Z" with no topic directory.
_EXCLUDED_BASENAME_PREFIXES = tuple(f"{t.upper()}_" for t in EXCLUDED_TOPICS)


def is_excluded_memory(name: str) -> bool:
    """True when `name` belongs to an excluded topic (spec/, report/,
    research/, project/).

    `name` is a memory name — an optional alias prefix, then path segments,
    then a basename, e.g. "spec/SPEC_X", "em/spec/SPEC_X", "report/REPORT_Y",
    "research/RESEARCH_Z", "project/PROJECT_Q", "dom/DOM_SPECIAL",
    "ref/REF_SPEC_PARSER", or a bare "SPEC_Z" with no topic segment at all.
    Case-insensitive; works on both already-normalized (lower-cased) and raw
    names.

    True when ANY path segment other than the basename equals an excluded
    topic (case-insensitive), OR the basename itself starts with one of the
    excluded-topic prefixes ("SPEC_", "REPORT_", "RESEARCH_", "PROJECT_",
    case-insensitive) — covering a bare "SPEC_Z" with no topic directory.
    """
    if not name:
        return False
    parts = name.split("/")
    basename = parts[-1]
    dirs = parts[:-1]
    for seg in dirs:
        if seg.lower() in EXCLUDED_TOPICS:
            return True
    basename_upper = basename.upper()
    if basename_upper.startswith(_EXCLUDED_BASENAME_PREFIXES):
        return True
    return False


def is_valid_memory_name(name: str) -> bool:
    """True when `name` (already normalized) looks like a real memory path.

    Guards against truncated/garbage tokens that a truncated hook message can
    leak into the stream (e.g. a literal 'ref/ref_...' ellipsis). Such a token
    must NEVER become a docpending link the sweep gate then demands be read or
    deferred — it names no real memory. Requires a 'dir/name' shape and rejects
    a trailing ellipsis or a name ending in an underscore stub.
    """
    if not name or '/' not in name:
        return False
    if '...' in name or '…' in name:
        return False
    tail = name.rsplit('/', 1)[-1]
    if not tail or tail.endswith('_') or tail.endswith('-'):
        return False
    return True


def count_edits_since_checkpoint(stream_path: str) -> int:
    """Count edit events since last checkpoint."""
    return count_events_since_last(stream_path, count_type='edit')


def count_searches_since_docread(stream_path: str) -> int:
    """Count consecutive search events since the last doc read / state change.

    A 'docread' event (appended when the agent reads a memory or lists
    memories) or a 'state' / 'checkpoint' event breaks the streak, so this
    counts only wide-reaching searches run WITHOUT consulting documentation.
    """
    return count_events_since_last(
        stream_path,
        marker_types=('state', 'checkpoint', 'docread'),
        count_type='search',
    )


# Events that end a run of undelegated main-agent work: a background
# delegation (Agent/Task with run_in_background, or Workflow), a state
# transition, or a checkpoint. Shared by the drift counter and the
# single-agent disarm lookup so both agree on what "since the last reset" means.
DRIFT_RESET_MARKERS = ('state', 'checkpoint', 'delegation')

# Tail window for drift scans. Larger than count_events_since_last's 10KB so a
# 'drift_hard_block' event survives a long disarmed solo run (~600 events).
DRIFT_SCAN_WINDOW_BYTES = 65536


def _events_since_drift_reset(stream_path: str) -> list:
    """Events (chronological) appended after the most recent
    DRIFT_RESET_MARKERS event, read from the last DRIFT_SCAN_WINDOW_BYTES of
    the stream. [] when the stream is missing or unreadable."""
    if not os.path.exists(stream_path):
        return []
    try:
        file_size = os.path.getsize(stream_path)
        with open(stream_path, 'r') as f:
            if file_size > DRIFT_SCAN_WINDOW_BYTES:
                f.seek(file_size - DRIFT_SCAN_WINDOW_BYTES)
                f.readline()  # Skip partial first line
            lines = f.readlines()
    except IOError:
        return []
    events = []
    for line in reversed(lines):
        try:
            event = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') in DRIFT_RESET_MARKERS:
            break
        events.append(event)
    events.reverse()
    return events


def _task_work_weight(event: dict) -> float:
    """Weight of one 'task_work' event: its 'w' field, or 1.0 when absent
    (events logged before weighting existed count at full weight)."""
    try:
        return float(event.get('w', 1.0))
    except (TypeError, ValueError):
        return 1.0


def count_task_work_since_delegation(stream_path: str) -> float:
    """WEIGHTED sum of main-agent 'task_work' events since the last drift
    reset (DRIFT_RESET_MARKERS) — the orchestrator-drift signal.

    swe_post_orchestrator_drift.py logs each task_work event with a weight
    'w': 1.0 for edits/writes/mutating Bash/foreground Agent, 0.5 for reads,
    searches, inspection/verification Bash and non-delegation MCP tools.
    Compared against DRIFT_THRESHOLD (6) / DRIFT_HARD_THRESHOLD (12).
    """
    return sum(_task_work_weight(e) for e in _events_since_drift_reset(stream_path)
               if e.get('type') == 'task_work')


def format_drift_weight(weight: float) -> str:
    """Render a weighted drift count: '12' for integral values, '6.5' else."""
    return str(int(weight)) if float(weight).is_integer() else f'{weight:.1f}'


# Weighted main-agent task-work since last reset at which the orchestrator-
# drift nudge (swe_post_orchestrator_drift.py) escalates from an advisory to
# a hard mandate, and the edit gate (swe_pre_edit_validate.py) starts
# hard-enforcing it. Shared here so both hooks read one constant.
DRIFT_HARD_THRESHOLD = 12

# A logged, deliberate exception recorded in the session's WM file: a
# genuinely tight single-file coupled fix that justifies continuing solo past
# DRIFT_HARD_THRESHOLD instead of splitting into parallel subagents.
SINGLE_AGENT_NOTE_RE = re.compile(r'single-agent\s*:', re.IGNORECASE)

# Stream event logged the FIRST time the hard threshold is reached in a run of
# undelegated work. Payload 'notes' = snapshot of the WM's single-agent lines
# at that moment; only a line NOT in that snapshot disarms the edit block.
DRIFT_HARD_BLOCK_EVENT = 'drift_hard_block'


def wm_has_single_agent_note(wm_content: str) -> bool:
    """True when `wm_content` (a session WM file's text) records a
    'single-agent: <reason>' override line, case-insensitive. Pure string
    check — callers resolve and read the WM file themselves. Presence alone
    NEVER disarms the drift block — see single_agent_disarmed."""
    return bool(SINGLE_AGENT_NOTE_RE.search(wm_content or ''))


def single_agent_note_lines(wm_content: str) -> list:
    """Sorted, de-duplicated, stripped WM lines carrying a 'single-agent:'
    note. Line identity is the comparison key for the hard-block snapshot."""
    return sorted({line.strip() for line in (wm_content or '').splitlines()
                   if SINGLE_AGENT_NOTE_RE.search(line)})


def last_drift_hard_block(stream_path: str):
    """Most recent 'drift_hard_block' event since the last drift reset, or
    None — a delegation/state/checkpoint reset re-arms the block."""
    for event in reversed(_events_since_drift_reset(stream_path)):
        if event.get('type') == DRIFT_HARD_BLOCK_EVENT:
            return event
    return None


def record_drift_hard_block(stream_path: str, wm_content: str,
                            session_id: str = '') -> dict:
    """Idempotently log the 'drift_hard_block' event for the current run of
    undelegated work, snapshotting the WM's existing single-agent lines.
    Returns the (existing or new) event. Called by both the drift post-hook
    (on reaching the hard threshold) and the edit pre-gate (on first deny),
    so a note written after EITHER announcement counts."""
    existing = last_drift_hard_block(stream_path)
    if existing is not None:
        return existing
    notes = single_agent_note_lines(wm_content)
    append_event(stream_path, DRIFT_HARD_BLOCK_EVENT, notes=notes, s=session_id)
    return {'type': DRIFT_HARD_BLOCK_EVENT, 'notes': notes}


def single_agent_disarmed(stream_path: str, wm_content: str) -> bool:
    """True when the drift hard block is disarmed: a 'drift_hard_block'
    event exists since the last reset AND the WM now holds a single-agent
    line absent from that event's snapshot. A note written BEFORE the block
    (pre-emptive) is in the snapshot and never disarms. The disarm ends at
    the next reset (delegation/state/checkpoint), whose next hard block
    snapshots the old note too."""
    event = last_drift_hard_block(stream_path)
    if event is None:
        return False
    snapshot = set(event.get('notes') or [])
    return any(line not in snapshot for line in single_agent_note_lines(wm_content))


# ---------------------------------------------------------------------------
# Init-gate degraded mode (circuit breaker for an unreachable Serena MCP)
# ---------------------------------------------------------------------------
# When the Serena MCP server is down, read_memory is unavailable, so the
# init-gate's mandatory read_memory("wf/WF_INIT") chain can never run — every
# other tool stays blanket-denied with no in-session escape (a hard deadlock).
# These pure, testable helpers implement a TWO-TIER circuit breaker:
#
#   Tier 1 "recovery" — DEGRADED_DENY_THRESHOLD (3) or more bare 'init_deny'
#   events since the last docread, with NO 'mcp_unavailable' recorded. This is
#   ambiguous: Serena may be fully reachable and the model is simply calling
#   the wrong tools (e.g. Bash/Grep) instead of read_memory. It unlocks ONLY
#   recovery/diagnostic commands — NOT general Read/Grep/Glob of the
#   codebase — because a working Serena means the correct fix is to read
#   wf/WF_INIT, not to grant broader tool access.
#
#   Tier 2 "degraded" — an 'mcp_unavailable' event since the last docread,
#   recorded by swe_post_tool_failure.py from a genuine Serena
#   connection-level failure. This is unambiguous: Serena is actually down,
#   so read-only tools (Read/Grep/Glob/LS/ToolSearch) and read-only Bash
#   unlock for real diagnosis and workaround.
#
# Both tiers clear the moment a 'docread' event appears.
DEGRADED_DENY_THRESHOLD = 3


def count_init_denies_since_docread(stream_path: str) -> int:
    """Count consecutive 'init_deny' events since the last 'docread'.

    A successful read_memory/list_memories call appends 'docread' elsewhere
    in the stream and therefore resets this streak — the circuit breaker only
    trips when the agent has made repeated init-gate attempts with NO
    intervening successful doc read, i.e. it genuinely cannot reach Serena.
    """
    return count_events_since_last(
        stream_path,
        marker_types=('docread',),
        count_type='init_deny',
    )


def has_mcp_unavailable_since_docread(stream_path: str) -> bool:
    """True when an 'mcp_unavailable' event (real Serena connection failure,
    from swe_post_tool_failure.py) has been recorded since the last docread."""
    if not os.path.exists(stream_path):
        return False
    return count_events_since_last(stream_path, marker_types=('docread',),
                                    count_type='mcp_unavailable') > 0


def is_degraded_tier2(stream_path: str) -> bool:
    """True when the session should be in Tier-2 'degraded' mode: a genuine
    Serena MCP connection failure was recorded (directly, or via the sticky
    'degraded' event stamped alongside the first 'mcp_unavailable'), since the
    last docread. Unlocks read-only tools broadly."""
    if not os.path.exists(stream_path):
        return False
    if has_mcp_unavailable_since_docread(stream_path):
        return True
    return count_events_since_last(stream_path, marker_types=('docread',),
                                    count_type='degraded') > 0


def is_degraded_tier1(stream_path: str) -> bool:
    """True when the session should be in Tier-1 'recovery' mode: bare
    denial count has reached DEGRADED_DENY_THRESHOLD since the last docread,
    WITH NO 'mcp_unavailable' recorded (Serena may still be fully reachable —
    unlocks recovery/diagnostic commands only, never general codebase
    Read/Grep/Glob)."""
    if not os.path.exists(stream_path):
        return False
    if has_mcp_unavailable_since_docread(stream_path):
        return False
    return count_init_denies_since_docread(stream_path) >= DEGRADED_DENY_THRESHOLD


def is_degraded(stream_path: str) -> bool:
    """True when the session is in EITHER degraded tier (1 or 2).

    Kept for backward compatibility with callers that only need to know
    "is some form of degraded mode active" — see is_degraded_tier1/tier2 for
    the tier-specific checks the init gate actually branches on.
    """
    return is_degraded_tier1(stream_path) or is_degraded_tier2(stream_path)


# ---------------------------------------------------------------------------
# Hardened read-only Bash classifier (shared by both tiers)
# ---------------------------------------------------------------------------
# Reject outright on any of these constructs, regardless of the primary
# command matched below — they enable output redirection, command
# substitution, or side-channel mutation that a primary-command allowlist
# alone cannot see (e.g. `cat f > /etc/hosts`, `` cat `id` ``,
# `grep x y | tee /etc/passwd`, `find . -exec rm {} \;`).
_BASH_DANGEROUS_TOKEN_RE = re.compile(
    r'`'                       # backtick command substitution
    r'|\$\('                  # $( ... ) command substitution
    r'|<\('                   # <( ... ) process substitution
    r'|>\('                   # >( ... ) process substitution
    r'|(?<!2)>>?(?!/dev/null|&1\b)'  # > or >> other than "2>/dev/null" / "2>&1"
    r'|\btee\b'
    r'|\bxargs\b'
    r'|-exec\b'
    r'|-execdir\b'
    r'|-delete\b'
    r'|\bsed\s+-i\b'
    r'|\bperl\s+-i\b'
)


def _bash_has_dangerous_construct(command: str) -> bool:
    """True when `command` contains a redirection/substitution/mutation
    construct that must reject the WHOLE command outright, independent of
    which primary commands appear. `2>/dev/null` and `2>&1` are the only
    permitted redirections (stderr suppression/merge for diagnostics)."""
    if not command:
        return False
    # Scrub the two allowed redirections first so the generic `>` check
    # below does not fire on them.
    scrubbed = command.replace('2>/dev/null', '').replace('2>&1', '')
    return bool(_BASH_DANGEROUS_TOKEN_RE.search(scrubbed))


def _split_bash_stages(command: str):
    """Split a Bash command into ;/&&/||/&/newline-separated GROUPS, then
    each group into |-separated STAGES, stripping simple leading env-var
    assignments from each stage. Returns a flat list of primary-command
    strings (one per stage across all groups)."""
    import re as _re
    groups = _re.split(r'(?:;|&&|\|\||&|\n)+', command)
    stages = []
    for group in groups:
        group = group.strip()
        if not group:
            continue
        for stage in _re.split(r'\|(?!\|)', group):
            stage = stage.strip()
            stage = _re.sub(
                r'^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S*)\s+)*',
                '', stage)
            if stage:
                stages.append(stage)
    return stages


# Paths under which recovery-mode log inspection (Tier 1) is permitted.
RECOVERY_LOG_PATH_PREFIXES = (
    '~/Library/Caches/claude-cli-nodejs/',
    '~/.cache/claude-cli-nodejs/',
    '~/.serena/logs/',
)


def _recovery_log_paths_ok(stage: str, project_root: str = '') -> bool:
    """True when every path-looking argument in `stage` (a cat/tail/head/ls/
    grep invocation) falls under one of RECOVERY_LOG_PATH_PREFIXES or the
    project's own .serena/ directory. Used only by Tier-1 recovery — this is
    intentionally narrower than the general read-only Bash classifier."""
    import os as _os
    import re as _re
    tokens = stage.split()[1:]  # drop the command name itself
    path_like = [t for t in tokens
                 if not t.startswith('-') and t not in ('2>/dev/null', '2>&1')]
    if not path_like:
        return False  # no path argument at all — nothing to validate as a log
    allowed_prefixes = list(RECOVERY_LOG_PATH_PREFIXES)
    if project_root:
        serena_dir = _os.path.join(project_root.rstrip('/'), '.serena')
        allowed_prefixes.append(serena_dir if serena_dir.endswith('/') else serena_dir + '/')
        allowed_prefixes.append('.serena/')
    for tok in path_like:
        # grep pattern arguments aren't paths — best-effort: only check tokens
        # that look like a path (contain '/' or start with ~ or .).
        if not (tok.startswith('~') or tok.startswith('/') or tok.startswith('.')):
            continue
        expanded = _os.path.expanduser(tok) if tok.startswith('~') else tok
        matched = False
        for prefix in allowed_prefixes:
            expanded_prefix = _os.path.expanduser(prefix)
            if expanded.startswith(expanded_prefix) or tok.startswith(prefix):
                matched = True
                break
        if not matched:
            return False
    return True


# Bash commands whose PRIMARY stage is read-only/diagnostic — allowed in
# Tier-2 degraded mode so the agent can inspect state and reconnect without
# being able to mutate anything. NOTE: unittest/pytest are deliberately
# EXCLUDED — they execute code, not merely inspect it.
DEGRADED_BASH_PRIMARY_RE = re.compile(
    r'^(?:'
    r'(?:cat|head|tail|less|more|grep|rg|find|ls|tree|pwd|wc|diff|file)\b'
    r'|ps\b|pgrep\b'
    r'|git\s+(?:status|log|diff|show|branch|rev-parse)\b'
    r')',
    re.IGNORECASE,
)

# `find` with any of these flags is a mutation/execution vector, not
# inspection — rejected even though `find` itself is in the allowlist above.
_FIND_DANGEROUS_FLAG_RE = re.compile(
    r'-exec\b|-execdir\b|-delete\b', re.IGNORECASE,
)

# git subcommands allowed in degraded/recovery Bash, and the flags that
# disqualify them (arbitrary config/output-file writes).
_GIT_READONLY_SUBCOMMAND_RE = re.compile(
    r'^git\s+(status|log|diff|show|branch|rev-parse)\b', re.IGNORECASE,
)
_GIT_DISQUALIFYING_FLAG_RE = re.compile(
    r'(?:^|\s)(-c\b|--output(?:=|\s)|-o\b)', re.IGNORECASE,
)


def _git_stage_is_readonly(stage: str) -> bool:
    """True when `stage` is an allowed read-only git subcommand with none of
    the disqualifying flags (-c, --output, -o)."""
    if not _GIT_READONLY_SUBCOMMAND_RE.match(stage):
        return False
    return not _GIT_DISQUALIFYING_FLAG_RE.search(stage)


def degraded_bash_is_readonly(command: str) -> bool:
    """True when EVERY stage of a Bash command is a read-only/diagnostic
    command, safe to allow in Tier-2 degraded mode.

    Hardened classifier: rejects outright on any dangerous construct
    (backtick/$()/<()/>()/redirection-other-than-2>/dev/null-or-2>&1/tee/
    xargs/-exec/-execdir/-delete/sed -i/perl -i), then requires EVERY
    ;/&&/||/&/newline/pipe-separated stage's primary command to be in the
    read-only allowlist. `python3 -m unittest` / `pytest` are NOT read-only
    (they execute code). git is allowed only for
    status/log/diff/show/branch/rev-parse without -c/--output/-o.
    """
    if not command or not command.strip():
        return False
    if _bash_has_dangerous_construct(command):
        return False
    stages = _split_bash_stages(command)
    if not stages:
        return False
    for stage in stages:
        if stage.lower().startswith('git '):
            if not _git_stage_is_readonly(stage):
                return False
            continue
        if stage.lower().startswith('find '):
            if _FIND_DANGEROUS_FLAG_RE.search(stage):
                return False
        if not DEGRADED_BASH_PRIMARY_RE.match(stage):
            return False
    return True


# Recovery-mode (Tier 1) diagnostic commands: `claude mcp` subcommands, ps/
# pgrep, and log inspection restricted to the documented cache/log paths.
_RECOVERY_CLAUDE_MCP_RE = re.compile(
    r'^claude\s+mcp\s+(list|get\b)', re.IGNORECASE,
)
_RECOVERY_PS_RE = re.compile(r'^(?:ps|pgrep)\b', re.IGNORECASE)
_RECOVERY_LOG_CMD_RE = re.compile(
    r'^(?:cat|tail|head|ls|grep)\b', re.IGNORECASE,
)


def recovery_bash_is_allowed(command: str, project_root: str = '') -> bool:
    """True when EVERY stage of `command` is a Tier-1 "recovery" diagnostic:
    `claude mcp list`/`claude mcp get ...`, `ps`/`pgrep`, or a
    cat/tail/head/ls/grep whose path arguments are all under
    RECOVERY_LOG_PATH_PREFIXES or the project's own .serena/ directory.

    Deliberately NOT the same as degraded_bash_is_readonly — Tier 1 fires
    while Serena may still be fully reachable, so it must not unlock general
    codebase inspection (grep/find/cat of source files), only the narrow set
    of commands needed to diagnose/reconnect Serena itself.
    """
    if not command or not command.strip():
        return False
    if _bash_has_dangerous_construct(command):
        return False
    stages = _split_bash_stages(command)
    if not stages:
        return False
    for stage in stages:
        if _RECOVERY_CLAUDE_MCP_RE.match(stage):
            continue
        if _RECOVERY_PS_RE.match(stage):
            continue
        if _RECOVERY_LOG_CMD_RE.match(stage):
            if _recovery_log_paths_ok(stage, project_root):
                continue
            return False
        return False
    return True


# Tool names always allowed in Tier-2 degraded mode (read-only harness tools).
DEGRADED_ALLOWED_TOOLS = frozenset(['Read', 'Grep', 'Glob', 'LS', 'ToolSearch'])


def is_manual_reset_cli(command: str) -> bool:
    """True when a Bash command invokes the manual init-gate reset CLI
    (swe_pre_tool_init_gate.py --reset-sentinel) — always allowed in either
    tier as the documented escape hatch alongside read-only diagnosis."""
    if not command:
        return False
    return 'swe_pre_tool_init_gate.py' in command and '--reset-sentinel' in command


def degraded_tool_allowed(tool_name: str, command: str = '') -> bool:
    """True when `tool_name` (with Bash's `command`) is permitted in Tier-2
    degraded mode: read-only inspection tools, hardened read-only Bash, and
    the manual reset CLI. Edit/Write/NotebookEdit and any other mutating Bash
    stay denied — degraded mode unlocks diagnosis, not task work."""
    if tool_name in DEGRADED_ALLOWED_TOOLS:
        return True
    if tool_name == 'Bash':
        return degraded_bash_is_readonly(command) or is_manual_reset_cli(command)
    return False


def recovery_tool_allowed(tool_name: str, command: str = '', project_root: str = '') -> bool:
    """True when `tool_name` (with Bash's `command`) is permitted in Tier-1
    recovery mode: ONLY recovery/diagnostic Bash (claude mcp list/get,
    ps/pgrep, restricted log reads) and the manual reset CLI. NOT general
    Read/Grep/Glob of the codebase — Tier 1 fires on ambiguous evidence
    (Serena may be fully reachable), so it must not unlock broad tool
    access, only the narrow path back to reading wf/WF_INIT."""
    if tool_name != 'Bash':
        return False
    return (recovery_bash_is_allowed(command, project_root)
            or is_manual_reset_cli(command))


DEGRADED_NOTICE = (
    "SWE degraded mode: Serena memory tools unreachable (mcp_unavailable). "
    "Read-only tools unlocked for diagnosis; reconnect Serena (/mcp) then "
    "read wf/WF_INIT."
)

RECOVERY_NOTICE = (
    "SWE recovery mode: 3+ denied tool calls with no successful doc read, "
    "but no confirmed Serena connection failure. Serena memory tools appear "
    "unreachable, so only recovery diagnostics are unlocked (claude mcp "
    "list/get, ps/pgrep, restricted log reads) — NOT general Read/Grep/Glob "
    "of the codebase. Ask the user to reconnect Serena via /mcp. If Serena "
    "is actually reachable, do not rely on this mode — instead read "
    "wf/WF_INIT via mcp__plugin_swe_serena__read_memory."
)


def count_all_events_since_last(stream_path: str, marker_type: str = 'continuation') -> int:
    """Count events of EVERY type since the most recent marker_type event.

    Same tail-read strategy as count_events_since_last. Used by the E1
    continuation re-emission rule: a directive suppressed as a same-state
    repeat is re-emitted once >=20 events have accumulated since it was last
    shown, so a long stretch of tool calls cannot outlive the guidance.
    """
    if not os.path.exists(stream_path):
        return 0
    try:
        file_size = os.path.getsize(stream_path)
        with open(stream_path, 'r') as f:
            if file_size > 10240:
                f.seek(max(0, file_size - 10240))
                f.readline()  # Skip partial first line
            lines = f.readlines()
        count = 0
        for line in reversed(lines):
            try:
                event = json.loads(line.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            if event.get('type') == marker_type:
                break
            count += 1
        return count
    except IOError:
        return 0


def has_event_since_last(stream_path: str, event_type: str,
                          marker_type: str = 'prompt') -> bool:
    """True when at least one `event_type` event has been appended since the
    most recent `marker_type` event (default marker: 'prompt', the per-turn
    boundary stamped at the top of swe_user_prompt_workflow.py's main()).

    Thin wrapper over count_events_since_last (count_type=event_type,
    marker_types=(marker_type,)) — DRY with the existing tail-read scanner
    rather than a second implementation. Used by the drift-advisory
    suppression: a 'direct_instruction' event since the last 'prompt' means
    THIS turn was a direct instruction, so the advisory should stay quiet.
    """
    return count_events_since_last(
        stream_path, marker_types=(marker_type,), count_type=event_type) > 0


def get_last_continuation(stream_path: str) -> str:
    """Return the `state` value of the most recent 'continuation' event, or
    '' if none exists yet. Used to suppress a repeated "CONTINUE (STATE): …"
    emission on every read/list/search when the state has not changed since
    it was last shown."""
    if not os.path.exists(stream_path):
        return ''
    try:
        with open(stream_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        return ''
    for line in reversed(lines):
        try:
            event = json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if event.get('type') == 'continuation':
            return event.get('state', '')
    return ''
