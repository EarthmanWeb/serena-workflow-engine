#!/usr/bin/env python3
"""PreToolUse gate - BLOCKS ruv-swarm swarm_init until FEATURE_SWARM is read.

Checks for a sentinel file created by swe_post_read_state.py when
FEATURE_SWARM memory is read. This enforces the mandatory reading
requirement from FEATURE_SWARM before any swarm initialization.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.stream import get_stream_dir
except ImportError:
    def extract_session_id(transcript_path):
        import re
        if not transcript_path:
            return None
        m = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
        return m.group(1)[:8] if m else None

    def get_stream_dir():
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())
        return os.path.join(project_dir, '.serena', 'streams')


def get_swarm_sentinel_path(session_id: str) -> str:
    """Get sentinel file path for FEATURE_SWARM read confirmation."""
    return os.path.join(get_stream_dir(), f'.swarm_feature_{session_id}')


def main():
    try:
        input_data = json.load(sys.stdin)
        transcript_path = input_data.get('transcript_path', '')
        session_id = extract_session_id(transcript_path)

        # Check sentinel file
        if session_id:
            sentinel = get_swarm_sentinel_path(session_id)
            if os.path.exists(sentinel):
                print(json.dumps({}))
                sys.exit(0)

        # BLOCK - FEATURE_SWARM not read
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"""🛑 BLOCKED: FEATURE_SWARM not read for session {session_id or 'unknown'}

═══════════════════════════════════════════════════════════════════════════════
               ⚠️  SWARM INITIALIZATION BLOCKED  ⚠️
═══════════════════════════════════════════════════════════════════════════════

You MUST read FEATURE_SWARM completely before initializing a swarm.

FEATURE_SWARM mandates reading these memories IN ORDER:
  1. WF_SWARM_ORCHESTRATE (primary workflow)
  2. REF_SWARM_PATTERNS (MCP tool patterns)
  3. CLAUDE_FLOW (coordination reference)
  4. REF_AGENTS (agent types)

MANDATORY ACTION - Call this tool NOW:
   → mcp__plugin_swe_serena__read_memory(memory_name="FEATURE_SWARM")

Then follow the mandatory reading steps listed in that memory.

═══════════════════════════════════════════════════════════════════════════════
          READ FEATURE_SWARM BEFORE SWARM INITIALIZATION
═══════════════════════════════════════════════════════════════════════════════"""
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"systemMessage": f"Swarm feature gate error: {e}"}))
        sys.exit(0)


if __name__ == '__main__':
    main()
