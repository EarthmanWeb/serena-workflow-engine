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
