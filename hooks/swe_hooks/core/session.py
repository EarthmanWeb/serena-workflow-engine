"""Session ID utilities for SWE hooks.

Centralizes session ID extraction and working memory session matching.
"""

import os
import re
import glob
from typing import Optional, Tuple


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
    """Find the MAIN project root by walking up directory tree.

    Skips any .serena folders inside .claude/plugins/ (nested plugin repos).
    Returns the highest .serena folder in the tree (main project).
    """
    current = os.path.abspath(start_dir)
    main_project_root = None

    while current != os.path.dirname(current):  # Stop at filesystem root
        serena_dir = os.path.join(current, '.serena')
        if os.path.isdir(serena_dir):
            # Only accept if NOT inside a plugin directory
            if '/.claude/plugins/' not in current and '\\.claude\\plugins\\' not in current:
                # Keep updating - we want the HIGHEST in the tree (main project)
                main_project_root = current
        current = os.path.dirname(current)

    return main_project_root if main_project_root else start_dir


def get_serena_memories_dir(cwd: str) -> str:
    """Get the .serena/memories directory path for WM files."""
    project_root = find_project_root(cwd)
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
        # Look for WM_<session_id>_* files specifically
        pattern = os.path.join(memories_dir, f'WM_{session_id}_*.md')
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
