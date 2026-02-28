#!/usr/bin/env python3
"""PostToolUse hook for TodoWrite - Direct WM sync.

When todos are modified, this hook writes the current todo state
directly into the WM file's Progress section. No model involvement —
the hook does the file write itself, then outputs empty (silent).

This avoids injecting directives that disrupt the model's tool-call
flow and cause conversation stop signals.
"""

import os
import sys
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session, get_project_root
    from swe_hooks.core.stream import get_stream_path, append_event
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostTodoWM")


# Marker comments used to fence the auto-synced todo block in WM
TODO_FENCE_START = '<!-- todo-sync-start -->'
TODO_FENCE_END = '<!-- todo-sync-end -->'


def format_todos(todos):
    """Format todo list items as markdown checklist lines.

    Args:
        todos: list of dicts with 'content' and 'status' keys
               (status: 'pending', 'in_progress', 'completed')

    Returns:
        String with markdown checklist lines
    """
    if not todos:
        return ''

    lines = []
    for todo in todos:
        content = todo.get('content', '')
        status = todo.get('status', 'pending')
        if status == 'completed':
            lines.append(f'- [x] {content}')
        elif status == 'in_progress':
            lines.append(f'- [~] {content} *(in progress)*')
        else:
            lines.append(f'- [ ] {content}')

    return '\n'.join(lines)


def sync_todos_to_wm(wm_path, todos):
    """Write formatted todos into WM file's Progress section.

    Uses fenced markers to replace only the auto-synced block,
    preserving any manually written progress notes.

    Args:
        wm_path: absolute path to the WM markdown file
        todos: list of todo dicts from TodoWrite tool_input
    """
    try:
        with open(wm_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except IOError:
        return

    todo_block = format_todos(todos)
    fenced_block = f'{TODO_FENCE_START}\n{todo_block}\n{TODO_FENCE_END}'

    # Case 1: Replace existing fenced block
    fence_pattern = re.compile(
        re.escape(TODO_FENCE_START) + r'.*?' + re.escape(TODO_FENCE_END),
        re.DOTALL
    )
    if fence_pattern.search(content):
        updated = fence_pattern.sub(fenced_block, content)
    else:
        # Case 2: Insert fenced block after ## Progress heading
        progress_match = re.search(r'^(##+ Progress.*?)$', content, re.MULTILINE)
        if progress_match:
            insert_pos = progress_match.end()
            updated = content[:insert_pos] + '\n\n' + fenced_block + '\n' + content[insert_pos:]
        else:
            # Case 3: No Progress section — append before ## Implementation Notes or at end
            notes_match = re.search(r'^## Implementation Notes', content, re.MULTILINE)
            if notes_match:
                insert_pos = notes_match.start()
                updated = content[:insert_pos] + '## Progress\n\n' + fenced_block + '\n\n' + content[insert_pos:]
            else:
                updated = content.rstrip() + '\n\n## Progress\n\n' + fenced_block + '\n'

    try:
        with open(wm_path, 'w', encoding='utf-8') as f:
            f.write(updated)
    except IOError:
        pass


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Track in stream
        if session_id:
            stream_path = get_stream_path(session_id)
            append_event(stream_path, 'todo', s=session_id)

        # Extract todos from tool_input
        tool_input = get_input_field(input_data, 'tool_input', default={})
        todos = tool_input.get('todos', [])

        if not todos or not session_id:
            output_empty()
            return

        # Find WM file for this session
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        wm_path = find_working_memory_for_session(cwd, session_id)

        if wm_path:
            sync_todos_to_wm(wm_path, todos)

        output_empty()

    except Exception:
        output_empty()


if __name__ == '__main__':
    main()
