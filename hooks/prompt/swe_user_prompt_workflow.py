#!/usr/bin/env python3
"""UserPromptSubmit hook - Ensure workflow state and provide instructions.

This hook fires on EVERY user prompt submission. It must:
1. Detect if prompt is a continuation of current task or a new task
2. Provide appropriate workflow instructions
3. Ensure Claude follows the workflow state machine

State is read from WM files (session-isolated), NOT a global state file.
"""

import os
import sys
import json
import re
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.config import (
        load_setup_complete,
        get_working_memory_filename, read_working_memory_state,
        read_state_file,
    )
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import get_stream_path, get_event_count
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "UserPromptSubmit")


# Patterns that indicate a continuation of the current task
# NOTE: No $ anchors — "okay, do that thing" should match, not just "okay"
CONTINUATION_PATTERNS = [
    r'^(yes|yeah|yep|yup|ok|okay|sure|continue|proceed|go ahead|keep going|next|do it)\b',
    r'^(sounds good|looks good|perfect|great|good|fine|alright)\b',
    r'^(please continue|please proceed|go on|carry on)\b',
    r'^(that\'?s? (good|great|fine|correct|right))\b',
    r'^(approved?|confirmed?|accept(ed)?)\b',
    r'^(all of them|do (all|both|everything|it all))\b',
    r'continue (with )?the',
    r'keep (working|going)',
    r'finish (the|this|it)',
    r'modify (the|this|it)',
    r'add (a|the|this|it)',
    r'complete (the|this|it)',
    # Conversational — questions/status checks about current work
    r'(are|is) (there|that|this|it) (fixed|done|ready|working|correct)',
    r'(did|does) (that|this|it) (work|fix|help|resolve)',
    r'(how|what).{0,20}(look|going|coming|progress)',
    r'any (other|more|further) (issues|problems|optimizations|suggestions|recommendations)',
    r'let me know (if|when|what)',
    r'(you should|should be|latest version|already committed)',
]

# Patterns that indicate an addition to the current task (not a new task)
ADDITION_PATTERNS = [
    r'^(also|additionally|and also|plus|another thing)',
    r'^(one more thing|by the way|btw)',
    r'^(can you also|could you also|please also)',
    r'^(don\'?t forget|remember to|make sure)',
    r'^(oh and|oh,? also)',
    r'^(while you\'?re at it|and also|also,?\s)',
    r'^(remove|change|update|tweak) (the|that|this)',
]

# Patterns that suggest a completely new task
NEW_TASK_PATTERNS = [
    r'^(new task|different task|change of plans|something else|switch to)',
    r'^(forget (that|the previous)|start over|start fresh|reset)',
    r'^(i want to|let\'?s? (work on|do|start))',
    r'^(help me (with|build|create|implement|add|fix|debug|review))',
    r'^(can you help|i need help|i need you to)',
    r'^(create|build|implement|add|fix|debug|review|analyze|refactor)',
    r'^(onboard|write|develop|make|design|setup|configure|install)',
]


def analyze_prompt(prompt: str, current_state: str) -> str:
    """
    Analyze prompt to determine intent.
    Returns: 'continuation', 'addition', 'new_task', or 'unknown'
    """
    prompt_lower = prompt.lower().strip()
    
    # Check for explicit continuation patterns
    for pattern in CONTINUATION_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return 'continuation'
    
    # Check for addition patterns
    for pattern in ADDITION_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return 'addition'
    
    # Check for explicit new task patterns
    for pattern in NEW_TASK_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return 'new_task'
    
    # Default: treat as unknown — do not assume intent from message length alone.
    # Short messages in active states could be new tasks, corrections, or questions.
    return 'unknown'



def main():
    try:
        # Read input
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except:
            pass
        
        prompt = input_data.get('prompt', '')
        cwd = input_data.get('cwd', os.getcwd())

        if not prompt or not prompt.strip():
            sys.exit(0)

        # Check setup
        setup = load_setup_complete(cwd)
        if not setup or not setup.get('complete'):
            # Handle setup acceptance — user says "yes" to bootstrap prompt
            if not setup or (not setup.get('complete') and not setup.get('bootstrapped')):
                if re.search(r'^(yes|yeah|yep|ok|sure|set.?up|initialize|init)\b', prompt_lower):
                    # Run bootstrap inline
                    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
                    bootstrap_script = os.path.join(plugin_root, 'scripts', 'swe-bootstrap.py') if plugin_root else ''
                    if not bootstrap_script or not os.path.exists(bootstrap_script):
                        # Fallback: resolve from this file's location
                        bootstrap_script = os.path.join(
                            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'scripts', 'swe-bootstrap.py'
                        )
                    if os.path.exists(bootstrap_script):
                        import subprocess
                        result = subprocess.run(
                            [sys.executable, bootstrap_script],
                            cwd=cwd, capture_output=True, text=True, timeout=30
                        )
                        if result.returncode == 0:
                            context = f"SWE Bootstrap Complete\n\n{result.stdout}\n\nMANDATORY NEXT ACTION:\n-> Run Skill(\"swe-scaffold-project\") to complete project setup."
                        else:
                            context = f"Bootstrap failed: {result.stderr}"
                    else:
                        context = "Bootstrap script not found at plugin root."
                    output = {
                        "hookSpecificOutput": {
                            "hookEventName": "UserPromptSubmit",
                            "additionalContext": context
                        }
                    }
                    print(json.dumps(output))
                    sys.exit(0)

            # Not yet set up — show gentle prompt (not block)
            if setup and setup.get('bootstrapped'):
                context = "SWE bootstrapped but not fully initialized. Run /swe-init or /swe-scaffold-project to complete."
            else:
                context = "SWE plugin detected but not initialized. Say \"yes\" to set up, or run the /swe-bypass command yourself to disable (user-only)."
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Extract session ID from transcript_path for session isolation
        transcript_path = input_data.get('transcript_path', '')
        session_id = extract_session_id(transcript_path)

        # Get current state — JSON state file is authoritative, WM is display artifact
        wm_file = None
        state_data = None

        if session_id:
            # Primary: read JSON state file directly (fast, no markdown parsing)
            sf = read_state_file(session_id)
            if sf:
                state_data = {
                    "current_state": sf.get("current_state", "WF_INIT"),
                    "session_id": sf.get("session_id", session_id),
                    "feature_keys": sf.get("features", []),
                    "task": sf.get("task", ""),
                    "progress": sf.get("progress", []),
                    "return_step": sf.get("return"),
                }
            # Also check if WM markdown exists (for display references)
            wm_filepath = find_working_memory_for_session(cwd, session_id)
            if wm_filepath:
                wm_file = os.path.basename(wm_filepath).replace('.md', '')

        # Session is valid if state file exists for this session
        should_reset = not state_data

        if should_reset:
            # No working memory for this session - start at WF_INIT
            current_state = "WF_INIT"
            wm_file = None  # Don't show old session's working memory
        else:
            current_state = state_data.get("current_state", "WF_INIT")

            # Ensure init sentinel exists for this session.
            # If WM is valid but sentinel is missing (e.g., mid-session pivot,
            # context compression, or sentinel cleanup), recreate it now.
            # This prevents the init gate deadlock where the daemon blocks
            # re-running the init chain but the gate demands it.
            if session_id and wm_file:
                try:
                    from swe_hooks.core.stream import get_sentinel_path
                    import time as _time
                    sentinel = get_sentinel_path(session_id)
                    if not os.path.exists(sentinel):
                        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
                        sentinel_data = {
                            "session_id": session_id,
                            "wm_file": wm_file,
                            "validated_at": int(_time.time()),
                        }
                        with open(sentinel, 'w') as f:
                            json.dump(sentinel_data, f, separators=(',', ':'))
                except (IOError, ImportError):
                    pass

        # Create StateManager for potential transitions
        state_mgr = StateManager(cwd, session_id=session_id)
        
        # Analyze prompt intent
        prompt_intent = analyze_prompt(prompt, current_state)
        
        # Handle WF_INIT state - always direct to WF_INIT workflow
        if current_state == 'WF_INIT':
            context = f"""<workflow-gate state="WF_INIT" session="{session_id or 'unknown'}">
<blocking-instruction priority="CRITICAL">
STOP. Your next action MUST be a tool call. Not text. A tool call.

Call this tool NOW:
mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")

- Do NOT output any text before calling this tool
- Do NOT explain what you're doing
- Do NOT acknowledge the user's message first
- Do NOT skip this because the user asked something specific
- The user's request will be handled AFTER you read WF_INIT

If your next output contains ANY text instead of a tool call, you have failed.
</blocking-instruction>
</workflow-gate>"""
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Handle completed/uninitialized states
        if current_state in ['UNINITIALIZED', 'WF_DONE', None]:
            # Check if we have a valid working memory for THIS session
            # If so, this is a "new task in same session" - preserve working memory
            is_same_session_new_task = (
                wm_file and
                session_id and
                current_state == 'WF_DONE'
            )

            if is_same_session_new_task:
                # Same session, new task after completion - go to WF_CLASSIFY, preserve WM
                state_mgr.transition_to('WF_CLASSIFY')
                current_state = 'WF_CLASSIFY'
                # Analyze the prompt to understand intent (don't force new_task)
                prompt_intent = analyze_prompt(prompt, current_state)
                if prompt_intent == 'unknown':
                    prompt_intent = 'same_session_new_task'  # Special case
            else:
                # Truly new session or no working memory - go to WF_START
                state_mgr.transition_to('WF_START')
                current_state = 'WF_START'
                prompt_intent = 'new_task'
        
        # Build context based on prompt intent and state
        if prompt_intent == 'continuation':
            # User is continuing - stay in current state, provide brief reminder
            if current_state == 'WF_START':
                # Haven't progressed - need to classify
                # Get stream event count for observability
                stream_info = ""
                if session_id:
                    stream_path = get_stream_path(session_id)
                    event_count = get_event_count(stream_path)
                    if event_count > 0:
                        stream_info = f"\nStream Events: {event_count}"
                context = f"""📋 WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

MANDATORY: Before responding, read and follow the WF_START workflow.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_START")
"""
            else:
                # In active state - continue workflow
                # Get stream event count for observability
                stream_info = ""
                if session_id:
                    stream_path = get_stream_path(session_id)
                    event_count = get_event_count(stream_path)
                    if event_count > 0:
                        stream_info = f"\nStream Events: {event_count}"
                context = f"""➡️ CONTINUING WORKFLOW: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

Continue with the current workflow step.
If you need to review instructions: mcp__plugin_swe_serena__read_memory(memory_name="wf/{current_state}")
"""
        
        elif prompt_intent == 'addition':
            # User is adding to current task - stay in current state
            # Get stream event count for observability
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            context = f"""➕ TASK ADDITION - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

This message may relate to the current task. Evaluate whether it adds to the current step or changes direction.
If scope changes significantly, transition to WF_CLASSIFY.
"""
        
        elif prompt_intent == 'same_session_new_task':
            # New task in same session after WF_DONE - preserve and update existing working memory
            # Get stream event count for observability
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            # Extract previous feature keys for fast-path detection
            prev_features = ""
            if state_data:
                fk = state_data.get("feature_keys", [])
                if fk:
                    prev_features = f"\nPrevious Feature(s): {', '.join(fk)}"

            context = f"""🔄 NEW TASK IN SAME SESSION - WORKFLOW STATE: {current_state}
Working Memory: {wm_file}{stream_info}{prev_features}
Session: {session_id}

**This is a NEW TASK in the SAME SESSION after completing WF_DONE.**

**DO NOT create a new WM file.** Update the existing WM ({wm_file}):
- Move previous task to `## Previous Task`
- Update `## Current Task` with the new task
- Reset `Edit Count Since Checkpoint` to 0

**Fast-path:** If the new task involves the SAME feature(s) as the previous task,
skip WF_CLASSIFY feature loading and go directly to WF_ARCH_REVIEW — the feature
memories are already loaded in context.

**Full path:** If the new task involves DIFFERENT feature(s), go to WF_CLASSIFY
to load the correct feature memories.

Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_CLASSIFY")
Or fast-path: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_ARCH_REVIEW")
"""

        elif prompt_intent == 'new_task':
            # New task - transition to WF_START
            if current_state not in ['WF_START', 'WF_INIT']:
                state_mgr.transition_to('WF_START')
                current_state = 'WF_START'

            # Get stream event count for observability
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            context = f"""🆕 NEW TASK DETECTED - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

MANDATORY: Before responding, read and follow the {current_state} workflow instructions.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/{current_state}")
"""
        
        else:
            # Unknown intent - route to WF_CLASSIFY for proper classification
            # Get stream event count for observability
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            if current_state == 'WF_START':
                context = f"""❓ INTENT UNCLEAR - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

MANDATORY: Before responding, read and follow WF_START to initialize.
Then proceed to WF_CLASSIFY for task classification.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/{current_state}")
"""
            else:
                # Transition to WF_CLASSIFY for classification
                state_mgr.transition_to('WF_CLASSIFY')
                context = f"""❓ INTENT UNCLEAR - Routing to WF_CLASSIFY
Working Memory: {wm_file or 'None'}{stream_info}

MANDATORY: Classify this task using WF_CLASSIFY.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_CLASSIFY")
"""
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": context
            }
        }
        print(json.dumps(output))
        sys.exit(0)
        
    except Exception as e:
        print(json.dumps({"systemMessage": f"Workflow hook error: {e}"}), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
