"""Stream-based event tracking. Append-only JSONL.

All hooks import this module to append events.
No separate hook process needed - piggybacks on existing hooks.

Events: {t: epoch, type: "tool|state|edit|checkpoint|interrupted", ...}
"""
import os
import json
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
                                    since_sweep: bool = False) -> set:
    """Collect normalized value_key values from count_type events since the
    current task started. A list-valued key contributes every element.

    Values are normalized lowercase with any '.md' suffix and 'mem:' prefix
    stripped; malformed/truncated names are dropped (see is_valid_memory_name).

    since_sweep=True narrows the window to after the last successful sweep as
    well as the task boundary (used for docpending accounting).
    """
    values = set()
    for event in events_since_task_start(stream_path, since_sweep=since_sweep):
        if event.get('type') != count_type:
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


def count_task_work_since_delegation(stream_path: str) -> int:
    """Count consecutive main-agent task-work events since the last delegation.

    A 'delegation' event (appended when the main agent launches an Agent or
    Workflow tool) resets the streak, so this counts only direct task work
    (Edit/Write/NotebookEdit/Serena edit tools/Bash) done in the main
    orchestrator thread WITHOUT fanning work out to subagents — the
    orchestrator-drift signal.
    """
    return count_events_since_last(
        stream_path,
        marker_types=('state', 'checkpoint', 'delegation'),
        count_type='task_work',
    )
