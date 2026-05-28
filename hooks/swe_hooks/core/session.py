"""Session ID utilities for SWE hooks.

Centralizes session ID extraction and working memory session matching.
"""

import os
import re
import glob
from typing import Optional, Tuple


# =============================================================================
# Project Root Resolution (CD-immune)
# =============================================================================


def get_project_root() -> str:
    """Get the project root directory reliably, immune to cd commands.

    Delegates to config.get_project_root() for single source of truth.
    Falls back to find_project_root() if config import fails.
    """
    try:
        from swe_hooks.core.config import get_project_root as _config_root
        return _config_root()
    except ImportError:
        return find_project_root(os.getcwd())


def extract_session_id(transcript_path: str) -> Optional[str]:
    """Extract 8-char session ID from transcript_path UUID.

    Args:
        transcript_path: Path like ~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl

    Returns:
        First 8 characters of the UUID, or None if not found
    """
    if not transcript_path:
        return None
    uuid_match = re.search(
        r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
        transcript_path
    )
    if uuid_match:
        return uuid_match.group(1)[:8]
    return None


def find_project_root(start_dir: str) -> str:
    """Find the project root by walking up looking for .git/.

    Uses .git/ (not .serena/) because .serena/ is created by the plugin
    itself — causes chicken-and-egg when cwd is a subdirectory.
    """
    current = os.path.abspath(start_dir)
    while current != os.path.dirname(current):
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        current = os.path.dirname(current)
    return start_dir


def get_serena_memories_dir(cwd: str = None) -> str:
    """Get the .serena/memories directory path for WM files.

    Args:
        cwd: Ignored - kept for backward compatibility. Uses get_project_root() instead.
    """
    project_root = get_project_root()
    return os.path.join(project_root, '.serena', 'memories')


def find_working_memory_for_session(cwd: str, session_id: Optional[str]) -> Optional[str]:
    """Find the working memory file for a specific session.

    Args:
        cwd: Working directory
        session_id: 8-char session ID

    Returns:
        Full path to the working memory file, or None if not found
    """
    memories_dir = get_serena_memories_dir(cwd)
    if not os.path.exists(memories_dir):
        return None

    if session_id:
        # Look for WM_<session_id>.md specifically
        pattern = os.path.join(memories_dir, f'WM_{session_id}.md')
        working_memories = glob.glob(pattern)
        if working_memories:
            # Return most recent by modification time
            return max(working_memories, key=os.path.getmtime)

    return None


def validate_working_memory_session(filepath: str, session_id: Optional[str]) -> bool:
    """Validate that a working memory file belongs to the specified session.

    Checks both filename and content for session ID.

    Args:
        filepath: Path to the working memory file
        session_id: Expected session ID

    Returns:
        True if the working memory belongs to this session
    """
    if not filepath or not os.path.exists(filepath):
        return False

    if not session_id:
        return True  # No session ID to validate against

    # Check filename first (faster)
    filename = os.path.basename(filepath)
    if session_id in filename:
        return True

    # Check content for Session ID field
    try:
        with open(filepath, 'r') as f:
            content = f.read(2000)  # Only need to check first part
        session_match = re.search(r'\*\*Session ID\*\*:\s*(\S+)', content)
        if session_match and session_match.group(1) == session_id:
            return True
    except IOError:
        pass

    return False


def get_session_context(input_data: dict, cwd: str) -> Tuple[Optional[str], Optional[str]]:
    """Get session ID and working memory path from hook input.

    Args:
        input_data: Hook input data with transcript_path
        cwd: Working directory

    Returns:
        Tuple of (session_id, wm_filepath) - either may be None
    """
    transcript_path = input_data.get('transcript_path', '')
    session_id = extract_session_id(transcript_path)
    wm_filepath = find_working_memory_for_session(cwd, session_id)
    return session_id, wm_filepath
