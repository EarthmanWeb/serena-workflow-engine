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


def collect_values_since_task_start(stream_path: str, count_type: str = 'docread',
                                    value_key: str = 'name') -> set:
    """Collect normalized value_key values from count_type events since the
    current task started.

    Task start = the LAST 'state' event whose to_s is WF_CLASSIFY (a follow-up
    task re-entering classification), or the last 'session_start' event if no
    such re-entry exists. Reads from a prior task NEVER satisfy the current
    task's sweep. Values are normalized lowercase with any '.md' suffix and
    'mem:' prefix stripped. Full-file scan — per-session streams are small.
    """
    if not os.path.exists(stream_path):
        return set()
    try:
        with open(stream_path, 'r') as f:
            lines = f.readlines()
    except IOError:
        return set()

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

    values = set()
    for event in events[start:]:
        if event.get('type') != count_type:
            continue
        value = event.get(value_key)
        if value:
            values.add(normalize_memory_name(str(value)))
    return values


def normalize_memory_name(name: str) -> str:
    """Normalize a memory name for comparison: lowercase, strip whitespace,
    'mem:' prefix, and '.md' suffix."""
    name = name.strip().lower()
    if name.startswith('mem:'):
        name = name[4:]
    if name.endswith('.md'):
        name = name[:-3]
    return name


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
