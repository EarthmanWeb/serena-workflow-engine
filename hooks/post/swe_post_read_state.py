#!/usr/bin/env python3
"""PostToolUse hook for read_memory - State transitions.

When a WF_* memory is read, this hook transitions the workflow state.
Uses session isolation to ensure state changes only affect the current session.
"""

import os
import sys
import json

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager, STATE_ICONS
    from swe_hooks.core.session import extract_session_id, get_project_root, find_working_memory_for_session
    from swe_hooks.core.config import append_transition_to_wm
    from swe_hooks.core.wm_writer_daemon import async_wm_write
    from datetime import datetime
    import re
    import time
except ImportError as e:
    output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"SWE import error: {e}"}}
    print(json.dumps(output), file=sys.stdout)
    sys.exit(0)


def update_test_docs_timestamp(wm_filepath: str, session_id: str) -> bool:
    """Update or add the Test Docs timestamp in working memory.

    Replaces any existing 'Test Docs: Read @<timestamp>' with current timestamp.
    If none exists, appends after the Workflow Context section.

    Returns True if successful.
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        current_timestamp = int(time.time())
        new_marker = f"Test Docs: Read @{current_timestamp}"

        # Pattern to match existing timestamp marker
        pattern = r'Test Docs: Read @\d+'

        if re.search(pattern, content):
            # Replace existing timestamp
            updated_content = re.sub(pattern, new_marker, content)
        else:
            # Add after Workflow Context section or at end of file
            context_match = re.search(r'(## Workflow Context\n(?:.*\n)*?)(\n## |\Z)', content)
            if context_match:
                insert_pos = context_match.end(1)
                updated_content = content[:insert_pos] + f"\n{new_marker}\n" + content[insert_pos:]
            else:
                # Fallback: append at end
                updated_content = content.rstrip() + f"\n\n{new_marker}\n"

        # Use async writer for safe background write
        return async_wm_write(
            filepath=wm_filepath,
            content=updated_content,
            operation_type='edit_tracking',
            validate=False,
            session_id=session_id
        )
    except Exception:
        return False


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        memory_name = get_input_field(input_data, 'tool_input', 'memory_file_name', default='')

        # Handle FEATURE_TESTS read - update timestamp in WM
        if memory_name == 'FEATURE_TESTS':
            transcript_path = get_input_field(input_data, 'transcript_path', default='')
            session_id = extract_session_id(transcript_path)
            wm_filepath = find_working_memory_for_session(cwd, session_id)
            if wm_filepath:
                update_test_docs_timestamp(wm_filepath, session_id)
                output_status(f"📖 Read: {memory_name} (timestamp updated)")
                return
            output_status(f"📖 Read: {memory_name}")
            return

        # Handle FEATURE_SWARM read - emit swarm directive
        if memory_name == 'FEATURE_SWARM':
            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"📖 Read: {memory_name}")
            output.add_message("")
            output.add_message("🐝 SWARM DETECTED - You MUST use ruv-swarm or hive-mind swarm orchestration. Go to WF_SWARM_ORCHESTRATE after completing WF_CLASSIFY feature loading.")
            output.output_and_exit()

        # Only process WF_* memories for state transitions
        if not memory_name or not memory_name.startswith('WF_'):
            output_status(f"📖 Read: {memory_name or 'unknown'}")
            return  # Explicit return for clarity (output_empty exits)

        # Extract session ID for session isolation
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Create state manager with session isolation
        state_mgr = StateManager(cwd, session_id=session_id)

        output = HookOutput(event_name="PostToolUse")
        icon = STATE_ICONS.get(memory_name, '📍')
        current = state_mgr.get_current_state()

        # Only transition if state is different
        if current != memory_name:
            # Create WM file when transitioning TO WF_START (end of WF_INIT)
            if memory_name == 'WF_START' and not state_mgr.wm_filepath:
                project_root = get_project_root()
                wm_filename = f"WM_{session_id}.md"
                wm_filepath = os.path.join(project_root, ".serena", "memories", wm_filename)

                wm_content = f"""# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: (awaiting classification)
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Workflow Context
**Current State**: WF_START
**Previous State**: WF_INIT

## Task Context
- **Feature(s)**: (to be determined)
- **Complexity**: (to be determined)

## Progress Tracking
### Pending
- [ ] Classify task

## Requirements
(to be determined from user request)

## Implementation Notes
(none yet)
"""
                os.makedirs(os.path.dirname(wm_filepath), exist_ok=True)
                with open(wm_filepath, 'w', encoding='utf-8') as f:
                    f.write(wm_content)

                # Update state manager with new WM
                state_mgr.set_working_memory(wm_filename.replace('.md', ''))
                output.add_message(f"✅ Working Memory created: {wm_filename}")

            success, msg = state_mgr.transition_to(memory_name)
            if success:
                output.add_message(f"{icon} ON STEP: {memory_name}")
                output.add_message(msg)
                # Auto-log transition to WM Progress section
                if state_mgr.wm_filepath:
                    append_transition_to_wm(state_mgr.wm_filepath, current, memory_name)
            else:
                # BLOCK invalid transition with clear instructions
                output.add_message(f"🛑 {msg}")
                output.add_message("")
                output.add_message("**YOU MUST STOP AND GO TO A VALID STATE.**")
                output.add_message("")
                output.add_message("The state machine enforces valid workflow paths.")
                output.add_message("You cannot skip steps in the workflow.")
                output.add_message("")
                output.add_message("**Common fixes:**")
                output.add_message("- From WF_START: Go to WF_CLASSIFY (for all tasks including operational)")
                output.add_message("- From WF_CLASSIFY: Go to WF_DETECT_REQ (simple) or WF_PLAN_ARCHITECTURE (complex)")
                output.add_message("- From WF_LOAD_FEATURE: Go to WF_ARCH_REVIEW (code changes) or WF_EXECUTE (operational tasks)")
                output.add_message("- Features must be loaded in WF_CLASSIFY or WF_LOAD_FEATURE before WF_EXECUTE")
        else:
            output.add_message(f"{icon} ON STEP: {memory_name}")

        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-read error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
