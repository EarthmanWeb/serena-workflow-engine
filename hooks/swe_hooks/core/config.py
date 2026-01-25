"""Configuration and path helpers for SWE hooks.

State is stored in WORKING_MEMORY files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

import json
import os
import re
import glob
from typing import Dict, Any, Optional, List, Tuple, Callable
from datetime import datetime

# Async write support - lazy import to avoid circular dependencies
_async_writer_available = None
_use_async_writes = True  # Set to False to disable async writes globally


def _get_async_writer():
    """Lazy import of async writer to avoid circular dependencies."""
    global _async_writer_available
    if _async_writer_available is None:
        try:
            from .wm_background_writer import async_wm_write, async_wm_append
            _async_writer_available = True
        except ImportError:
            _async_writer_available = False
    return _async_writer_available


def set_async_writes_enabled(enabled: bool):
    """Enable or disable async writes globally."""
    global _use_async_writes
    _use_async_writes = enabled


def is_async_writes_enabled() -> bool:
    """Check if async writes are enabled and available."""
    return _use_async_writes and _get_async_writer()


def get_project_root() -> str:
    """Get project root from CLAUDE_PROJECT_DIR env var (set by Claude Code).

    This is the official, documented way to get the project root.
    Immune to cd commands changing the working directory.
    """
    # Primary: CLAUDE_PROJECT_DIR - set by Claude Code, never changes
    project_dir = os.environ.get('CLAUDE_PROJECT_DIR', '')
    if project_dir:
        return project_dir

    # Fallback: walk up from cwd (less reliable after cd)
    current = os.getcwd()
    while current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, '.serena')):
            return current
        current = os.path.dirname(current)
    return os.getcwd()


def get_paths(cwd: str = None) -> Dict[str, str]:
    """Get all relevant paths based on project root.

    Args:
        cwd: Ignored - kept for backward compatibility.
    """
    project_root = get_project_root()
    return {
        "cwd": cwd,
        "project_root": project_root,
        "claude_dir": os.path.join(project_root, ".claude"),
        "setup_file": os.path.join(project_root, ".claude", "plugins", "serena-workflow-engine", "swe-setup-complete.json"),
        "learning_file": os.path.join(project_root, ".claude", "learning.json"),
        "plugin_dir": os.path.join(project_root, ".claude", "plugins", "swe"),
        "instructions_dir": os.path.join(project_root, ".claude", "plugins", "swe", "memories", "instructions"),
        "references_dir": os.path.join(project_root, ".claude", "plugins", "swe", "memories", "references"),
        "serena_memories": os.path.join(project_root, ".serena", "memories"),
    }


# =============================================================================
# WORKING_MEMORY-based State Management (Session-Isolated)
# =============================================================================

def find_working_memory_files(cwd: str) -> List[str]:
    """Find all WORKING_MEMORY files, sorted by date (newest first)."""
    paths = get_paths(cwd)
    memories_dir = paths["serena_memories"]
    
    if not os.path.exists(memories_dir):
        return []
    
    pattern = os.path.join(memories_dir, "WM_*.md")
    files = glob.glob(pattern)
    
    # Sort by filename (which includes timestamp) in reverse order
    files.sort(reverse=True)
    return files


def get_most_recent_working_memory(cwd: str) -> Optional[str]:
    """Get the most recent WORKING_MEMORY file path."""
    files = find_working_memory_files(cwd)
    return files[0] if files else None


def get_working_memory_filename(cwd: str) -> Optional[str]:
    """Get just the filename (without path) of the most recent WORKING_MEMORY."""
    filepath = get_most_recent_working_memory(cwd)
    if filepath:
        return os.path.basename(filepath).replace('.md', '')
    return None


def parse_working_memory_state(content: str) -> Dict[str, Any]:
    """Parse workflow state from WORKING_MEMORY markdown content.
    
    Extracts state from the '## Workflow Context' section.
    """
    state = {
        "current_state": "WF_INIT",
        "feature_keys": [],
        "session_id": None,
        "return_step": None,
        "invocation_mode": "workflow",
        "status": "Starting",
    }
    
    # Find the Workflow Context section
    wf_match = re.search(r'## Workflow Context\s*\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    if wf_match:
        wf_section = wf_match.group(1)
        
        # Parse key-value pairs
        # Current State takes priority (explicit state for stop hook)
        current_state = re.search(r'\*\*Current State\*\*:\s*(\S+)', wf_section)
        if current_state:
            state["current_state"] = current_state.group(1)
        else:
            # Fall back to Calling Step for backward compatibility
            calling_step = re.search(r'\*\*Calling Step\*\*:\s*(\S+)', wf_section)
            if calling_step:
                state["current_state"] = calling_step.group(1)
        
        feature_keys = re.search(r'\*\*Feature Key\(s\)\*\*:\s*(.+)', wf_section)
        if feature_keys:
            state["feature_keys"] = [k.strip() for k in feature_keys.group(1).split(',')]
        
        session_id = re.search(r'\*\*Session ID\*\*:\s*(\S+)', wf_section)
        if session_id:
            state["session_id"] = session_id.group(1)
        
        return_step = re.search(r'\*\*Return Step\*\*:\s*(\S+)', wf_section)
        if return_step:
            state["return_step"] = return_step.group(1)
        
        invocation_mode = re.search(r'\*\*Invocation Mode\*\*:\s*(\S+)', wf_section)
        if invocation_mode:
            state["invocation_mode"] = invocation_mode.group(1)
    
    # Also parse Session Context for status
    status_match = re.search(r'\*\*Status\*\*:\s*(.+)', content)
    if status_match:
        state["status"] = status_match.group(1).strip()
    
    return state


def update_working_memory_state(content: str, new_state: str, return_step: str = None) -> str:
    """Update the workflow state in WORKING_MEMORY content.

    Modifies the '## Workflow Context' section with new state.
    Returns the updated content.
    """
    # Update Current State (primary field for stop hook)
    if re.search(r'\*\*Current State\*\*:', content):
        content = re.sub(
            r'(\*\*Current State\*\*:\s*)\S+',
            f'\\g<1>{new_state}',
            content
        )

    # Update Calling Step (for backward compatibility)
    content = re.sub(
        r'(\*\*Calling Step\*\*:\s*)\S+',
        f'\\g<1>{new_state}',
        content
    )
    
    # Update Return Step if provided
    if return_step:
        content = re.sub(
            r'(\*\*Return Step\*\*:\s*)\S+',
            f'\\g<1>{return_step}',
            content
        )
    
    # Update Last Updated timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if re.search(r'## Last Updated', content):
        content = re.sub(
            r'(## Last Updated\s*\n).*',
            f'\\g<1>{timestamp}',
            content
        )
    
    return content


# =============================================================================
# WORKING_MEMORY Staleness Detection (for enforcement)
# =============================================================================

def get_wm_last_updated(content: str) -> Optional[datetime]:
    """Extract the last updated timestamp from WORKING_MEMORY content.
    
    Looks for patterns like:
    - **Last Updated:** 2026-01-22T14:30:00Z
    - **Edit Count Since Checkpoint:** N
    """
    # Try ISO format first
    match = re.search(r'\*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)', content)
    if match:
        try:
            ts = match.group(1).replace('T', ' ')[:16]  # Normalize to YYYY-MM-DD HH:MM
            return datetime.strptime(ts, "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    
    # Try simpler date format
    match = re.search(r'\*\*Last Updated\*\*:\s*(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', content)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    
    return None


def get_wm_edit_count(content: str) -> int:
    """Extract the edit count from WORKING_MEMORY content."""
    match = re.search(r'\*\*Edit Count Since Checkpoint\*\*:\s*(\d+)', content)
    if match:
        return int(match.group(1))
    return 0


def update_wm_edit_tracking(content: str, edit_count: int, edited_files: List[str] = None) -> str:
    """Update edit tracking metadata in WORKING_MEMORY content.
    
    Updates or adds:
    - **Last Updated:** timestamp
    - **Edit Count Since Checkpoint:** N
    - **Recent Edits:** list of files
    """
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Update or add Last Updated
    if re.search(r'\*\*Last Updated\*\*:', content):
        content = re.sub(
            r'(\*\*Last Updated\*\*:\s*).*',
            f'\\g<1>{timestamp}',
            content
        )
    else:
        # Add to Progress section if it exists
        if '## Progress' in content:
            content = re.sub(
                r'(## Progress\s*\n)',
                f'\\g<1>\n**Last Updated:** {timestamp}\n',
                content
            )
    
    # Update or add Edit Count
    if re.search(r'\*\*Edit Count Since Checkpoint\*\*:', content):
        content = re.sub(
            r'(\*\*Edit Count Since Checkpoint\*\*:\s*)\d+',
            f'\\g<1>{edit_count}',
            content
        )
    else:
        # Add after Last Updated if present, otherwise to Progress section
        if re.search(r'\*\*Last Updated\*\*:', content):
            content = re.sub(
                r'(\*\*Last Updated\*\*:.*\n)',
                f'\\g<1>**Edit Count Since Checkpoint:** {edit_count}\n',
                content
            )
    
    # Update Recent Edits list
    if edited_files:
        edits_str = ', '.join([f'`{f}`' for f in edited_files[-5:]])  # Keep last 5
        if re.search(r'\*\*Recent Edits\*\*:', content):
            content = re.sub(
                r'(\*\*Recent Edits\*\*:\s*).*',
                f'\\g<1>{edits_str}',
                content
            )
        else:
            if re.search(r'\*\*Edit Count Since Checkpoint\*\*:', content):
                content = re.sub(
                    r'(\*\*Edit Count Since Checkpoint\*\*:.*\n)',
                    f'\\g<1>**Recent Edits:** {edits_str}\n',
                    content
                )
    
    return content


def reset_wm_edit_tracking(content: str) -> str:
    """Reset edit tracking after a checkpoint (user updated progress)."""
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Update Last Updated
    if re.search(r'\*\*Last Updated\*\*:', content):
        content = re.sub(
            r'(\*\*Last Updated\*\*:\s*).*',
            f'\\g<1>{timestamp}',
            content
        )
    
    # Reset Edit Count to 0
    if re.search(r'\*\*Edit Count Since Checkpoint\*\*:', content):
        content = re.sub(
            r'(\*\*Edit Count Since Checkpoint\*\*:\s*)\d+',
            '\\g<1>0',
            content
        )
    
    # Clear Recent Edits
    if re.search(r'\*\*Recent Edits\*\*:', content):
        content = re.sub(
            r'\*\*Recent Edits\*\*:.*\n',
            '',
            content
        )
    
    return content


def check_wm_staleness(cwd: str, wm_filepath: str, edit_threshold: int = 3) -> Tuple[bool, int, Optional[datetime]]:
    """Check if WORKING_MEMORY is stale based on edit tracking.
    
    Args:
        cwd: Working directory
        wm_filepath: Path to the WORKING_MEMORY file
        edit_threshold: Number of edits before considered stale
    
    Returns:
        Tuple of (is_stale, edit_count, last_update_time)
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False, 0, None
    
    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()
        
        edit_count = get_wm_edit_count(content)
        last_updated = get_wm_last_updated(content)
        
        is_stale = edit_count >= edit_threshold
        return is_stale, edit_count, last_updated
    except IOError:
        return False, 0, None


def check_wm_progress_updated(cwd: str, wm_filepath: str, since_timestamp: datetime = None) -> bool:
    """Check if WORKING_MEMORY Progress section was updated since timestamp.
    
    Args:
        cwd: Working directory
        wm_filepath: Path to the WORKING_MEMORY file
        since_timestamp: Check if updated after this time. If None, checks if edit count is 0.
    
    Returns:
        True if progress was updated (edit count is 0 or last_updated > since_timestamp)
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return True  # No WM to check - allow operation
    
    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()
        
        edit_count = get_wm_edit_count(content)
        
        # If edit count is 0, WM was updated after last checkpoint
        if edit_count == 0:
            return True
        
        # If we have a timestamp to check against
        if since_timestamp:
            last_updated = get_wm_last_updated(content)
            if last_updated and last_updated > since_timestamp:
                return True
        
        return False
    except IOError:
        return True  # On error, allow operation


def persist_edit_to_wm(cwd: str, wm_filepath: str, edited_file: str = None,
                       async_mode: bool = None) -> Tuple[bool, int]:
    """Persist an edit to WORKING_MEMORY tracking.

    Args:
        cwd: Working directory
        wm_filepath: Path to the WORKING_MEMORY file
        edited_file: Optional file path that was edited
        async_mode: Override async behavior (None = use global setting)

    Returns:
        Tuple of (success, new_edit_count)
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False, 0

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        # Get current edit count and increment
        current_count = get_wm_edit_count(content)
        new_count = current_count + 1

        # Get recent edits list
        recent_match = re.search(r'\*\*Recent Edits\*\*:\s*(.+)', content)
        recent_files = []
        if recent_match:
            # Parse existing files
            recent_str = recent_match.group(1)
            recent_files = [f.strip('`').strip() for f in recent_str.split(',') if f.strip()]

        # Add new file if provided
        if edited_file:
            # Clean up file path
            clean_path = edited_file.replace(cwd, '').lstrip('/')
            if clean_path not in recent_files:
                recent_files.append(clean_path)

        # Update content
        updated_content = update_wm_edit_tracking(content, new_count, recent_files)

        # Determine if async write should be used
        use_async = async_mode if async_mode is not None else is_async_writes_enabled()

        if use_async:
            # Use async background writer
            from .wm_background_writer import async_wm_write
            success = async_wm_write(
                filepath=wm_filepath,
                content=updated_content,
                operation_type='edit_tracking',
                validate=False,  # Edit tracking doesn't need full validation
                old_content=content,
            )
            return success, new_count
        else:
            # Synchronous write (original behavior)
            with open(wm_filepath, 'w') as f:
                f.write(updated_content)
            return True, new_count
    except IOError:
        return False, 0


def append_transition_to_wm(wm_filepath: str, from_state: str, to_state: str,
                            async_mode: bool = None) -> bool:
    """Append a state transition note to WORKING_MEMORY Progress section.

    Args:
        wm_filepath: Path to the WORKING_MEMORY file
        from_state: Previous workflow state
        to_state: New workflow state
        async_mode: Override async behavior (None = use global setting)

    Returns:
        True if successful, False otherwise
    """
    if not wm_filepath or not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        timestamp = datetime.now().strftime("%H:%M")
        transition_note = f"- [{timestamp}] Transitioned: {from_state} → {to_state}"

        # Find Progress section and append transition note
        progress_match = re.search(r'(## Progress\s*\n)(.*?)(?=\n## |\Z)', content, re.DOTALL)
        updated_content = content

        if progress_match:
            progress_section = progress_match.group(2)

            # Check if there's already a Transitions subsection
            if '### Transitions' in progress_section:
                # Append to existing Transitions subsection
                updated_content = re.sub(
                    r'(### Transitions\s*\n.*?)(\n###|\n##|\Z)',
                    f'\\g<1>{transition_note}\n\\g<2>',
                    content,
                    flags=re.DOTALL
                )
            else:
                # Add Transitions subsection before the next section or at end of Progress
                insert_pos = progress_match.end()
                updated_content = content[:insert_pos] + f"\n### Transitions\n{transition_note}\n" + content[insert_pos:]

        # Determine if async write should be used
        use_async = async_mode if async_mode is not None else is_async_writes_enabled()

        if use_async:
            # Use async background writer
            from .wm_background_writer import async_wm_write
            return async_wm_write(
                filepath=wm_filepath,
                content=updated_content,
                operation_type='transition_log',
                validate=False,  # Transition logging doesn't need full validation
                old_content=content,
            )
        else:
            # Synchronous write (original behavior)
            with open(wm_filepath, 'w') as f:
                f.write(updated_content)
            return True
    except IOError:
        return False


def read_working_memory_state(cwd: str, wm_filename: str = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Read state from a WORKING_MEMORY file.
    
    Args:
        cwd: Working directory
        wm_filename: Optional specific WORKING_MEMORY filename (without .md)
                    If None, uses most recent WORKING_MEMORY file
    
    Returns:
        Tuple of (state_dict, wm_filepath) or (None, None) if not found
    """
    paths = get_paths(cwd)
    
    if wm_filename:
        filepath = os.path.join(paths["serena_memories"], f"{wm_filename}.md")
    else:
        filepath = get_most_recent_working_memory(cwd)
    
    if not filepath or not os.path.exists(filepath):
        return None, None
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        state = parse_working_memory_state(content)
        return state, filepath
    except IOError:
        return None, None


def write_working_memory_state(cwd: str, wm_filepath: str, new_state: str,
                                return_step: str = None, async_mode: bool = None) -> bool:
    """Update state in a WORKING_MEMORY file.

    Args:
        cwd: Working directory
        wm_filepath: Full path to the WORKING_MEMORY file
        new_state: New workflow state (e.g., 'WF_EXECUTE')
        return_step: Optional return step to set
        async_mode: Override async behavior (None = use global setting)

    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(wm_filepath):
        return False

    try:
        with open(wm_filepath, 'r') as f:
            content = f.read()

        updated_content = update_working_memory_state(content, new_state, return_step)

        # Determine if async write should be used
        use_async = async_mode if async_mode is not None else is_async_writes_enabled()

        if use_async:
            # Use async background writer with anti-pattern detection
            from .wm_background_writer import async_wm_write
            return async_wm_write(
                filepath=wm_filepath,
                content=updated_content,
                operation_type='state_update',
                validate=True,  # State updates should be validated
                old_content=content,  # For anti-pattern detection
            )
        else:
            # Synchronous write (original behavior)
            with open(wm_filepath, 'w') as f:
                f.write(updated_content)
            return True
    except IOError:
        return False


# =============================================================================
# Legacy Compatibility Layer
# These functions now use WORKING_MEMORY as the source of truth
# =============================================================================

def load_workflow_state(cwd: str, wm_filename: str = None) -> Optional[Dict[str, Any]]:
    """Load workflow state from WORKING_MEMORY file.
    
    NOTE: State is now stored in WORKING_MEMORY files, not a global JSON file.
    This allows multiple concurrent sessions without state conflicts.
    """
    state, filepath = read_working_memory_state(cwd, wm_filename)
    
    if state is None:
        return None
    
    # Convert to legacy format for backward compatibility
    return {
        "session_id": state.get("session_id"),
        "current_state": state.get("current_state", "WF_INIT"),
        "previous_state": None,
        "working_memory_file": os.path.basename(filepath).replace('.md', '') if filepath else None,
        "edits_since_checkpoint": 0,
        "is_swarm_agent": False,
        "plan_mode": False,
        "trajectory_id": None,
        "trajectory_steps": 0,
        "reward_signals": {
            "state_transitions": 0,
            "clarify_count": 0,
            "edit_count": 0,
        }
    }


def save_workflow_state(cwd: str, state: Dict[str, Any], wm_filepath: str = None) -> bool:
    """Save workflow state to WORKING_MEMORY file.
    
    NOTE: If no wm_filepath provided, finds the most recent WORKING_MEMORY.
    """
    if wm_filepath is None:
        wm_filepath = get_most_recent_working_memory(cwd)
    
    if wm_filepath is None:
        # No WORKING_MEMORY file exists - can't save state
        # This is expected at session start before WM is created
        return False
    
    new_state = state.get("current_state", "WF_INIT")
    return write_working_memory_state(cwd, wm_filepath, new_state)


def load_setup_status(cwd: str) -> Optional[Dict[str, Any]]:
    """Load setup completion status."""
    paths = get_paths(cwd)
    setup_file = paths["setup_file"]

    if not os.path.exists(setup_file):
        return None

    try:
        with open(setup_file, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# Alias for backward compatibility
load_setup_complete = load_setup_status


def save_setup_complete(cwd: str, status: Dict[str, Any]) -> bool:
    """Save setup completion status."""
    paths = get_paths(cwd)
    setup_file = paths["setup_file"]
    os.makedirs(os.path.dirname(setup_file), exist_ok=True)
    try:
        with open(setup_file, 'w') as f:
            json.dump(status, f, indent=2)
        return True
    except IOError:
        return False


def get_reference_content(cwd: str, ref_name: str) -> Optional[str]:
    """Get content of a reference file."""
    paths = get_paths(cwd)
    ref_file = os.path.join(paths["references_dir"], f"{ref_name}.md")
    if os.path.exists(ref_file):
        try:
            with open(ref_file, 'r') as f:
                return f.read()
        except IOError:
            return None
    return None


def is_setup_complete(cwd: str) -> bool:
    """Check if initial setup is complete."""
    status = load_setup_status(cwd)
    return status is not None and status.get("complete", False)


def generate_session_id() -> str:
    """Generate a new session ID based on timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def generate_trajectory_id() -> str:
    """Generate a trajectory ID for RLVR learning."""
    import random
    return f"traj_{int(datetime.now().timestamp())}_{random.randint(10000, 99999)}"


def create_initial_state(session_id: str = None) -> Dict[str, Any]:
    """Create initial workflow state."""
    if session_id is None:
        session_id = generate_session_id()

    return {
        "session_id": session_id,
        "current_state": "UNINITIALIZED",
        "previous_state": None,
        "edits_since_checkpoint": 0,
        "is_swarm_agent": False,
        "plan_mode": False,
        "plan_mode_entries": 0,
        "plan_mode_reason": None,
        "working_memory_file": None,
        "trajectory_id": generate_trajectory_id(),
        "trajectory_steps": 0,
        "learning_complete": False,
        "computed_reward": None,
        "reward_signals": {
            "skill_returns": [],
            "state_transitions": 0,
            "clarify_count": 0,
            "edit_count": 0,
            "checkpoint_compliance": 1.0,
            "test_pass_rate": None,
            "arch_review_pass": None,
            "verify_success": None
        },
        "is_claude_flow_agent": True
    }
