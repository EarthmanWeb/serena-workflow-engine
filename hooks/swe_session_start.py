#!/usr/bin/env python3
"""SessionStart hook - Initialize WF_INIT workflow using WM.

State is stored in WM files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

import os
import sys
import json
from datetime import datetime

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.config import (
        load_setup_complete,
        get_most_recent_working_memory, get_working_memory_filename,
        read_working_memory_state, get_paths
    )
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.wm_background_writer import async_wm_write
except ImportError as e:
    print(json.dumps({"systemMessage": f"SWE import error: {e}"}), file=sys.stdout)
    sys.exit(0)





def main():
    try:
        # Read input
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except:
            pass
        
        cwd = input_data.get('cwd', os.getcwd())
        
        # Extract unique session ID from transcript_path (contains UUID per conversation)
        # This ensures each chat gets its own isolated session
        transcript_path = input_data.get('transcript_path', '')
        if transcript_path:
            # Extract UUID from path like ~/.claude/projects/.../00893aaf-19fa-41d2-8238-13269b9b3ca0.jsonl
            import re
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
            if uuid_match:
                session_id = uuid_match.group(1)[:8]  # Use first 8 chars for brevity
            else:
                session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        else:
            session_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Check setup
        setup = load_setup_complete(cwd)
        if not setup or not setup.get('complete'):
            # First-time project setup NOT complete - this is different from session init
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": """🛑🛑🛑 CRITICAL: PROJECT SETUP NOT COMPLETE 🛑🛑🛑

═══════════════════════════════════════════════════════════════════════════════
                    ⚠️  FIRST-TIME SETUP REQUIRED  ⚠️
═══════════════════════════════════════════════════════════════════════════════

This is a ONE-TIME setup for the project (not per-session).

MANDATORY: Run /swe-init to complete first-time project setup.

This installs:
- MCP server configurations
- Workflow instruction files
- Core memory templates
- Git ignore entries

After /swe-init completes, restart Claude Code and return to this project.

═══════════════════════════════════════════════════════════════════════════════
              DO NOT ATTEMPT ANY OTHER ACTIONS UNTIL SETUP COMPLETE
═══════════════════════════════════════════════════════════════════════════════"""
                }
            }
            print(json.dumps(output))
            sys.exit(0)

        # ALWAYS start fresh - never resume old working memory from previous sessions
        # Each chat/conversation is a NEW session with its own working memory
        # Auto-create WM file with placeholder descriptor
        # Claude should rename to WM_{session_id}_{task_descriptor}.md once task is known

        # Get project root from CLAUDE_PROJECT_DIR (set by Claude Code)
        from swe_hooks.core.session import get_project_root
        project_root = get_project_root()

        wm_filename = f"WM_{session_id}_session.md"  # Placeholder - rename after task classification
        wm_filepath = os.path.join(project_root, ".serena", "memories", wm_filename)

        # Create initial WM content
        wm_content = f"""# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: (awaiting user task)
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Workflow Context
**Current State**: WF_INIT
**Previous State**: None

## Task Context
- **Feature(s)**: (to be determined)
- **Complexity**: (to be determined)

## Progress Tracking
### Pending
- [ ] Await user task

## Requirements
(to be determined from user request)

## Implementation Notes
(none yet)
"""

        # Write WM file synchronously (must exist before init_gate runs)
        os.makedirs(os.path.dirname(wm_filepath), exist_ok=True)
        with open(wm_filepath, 'w', encoding='utf-8') as f:
            f.write(wm_content)

        context = f"""🚀 SERENA WORKFLOW ENGINE - Session {session_id}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Working Memory: {wm_filename} (auto-created)
Current State: WF_INIT

═══════════════════════════════════════════════════════════════════════════════
STEP 1: Read WF_INIT workflow instructions
   → mcp__plugin_swe_serena__read_memory("WF_INIT")

STEP 2: Follow WF_INIT to classify and execute user's task
═══════════════════════════════════════════════════════════════════════════════
"""

        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"systemMessage": f"Session start error: {e}"}), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()