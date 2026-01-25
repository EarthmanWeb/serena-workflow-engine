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

PLUGIN_ROOT = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
if PLUGIN_ROOT:
    hooks_dir = os.path.join(PLUGIN_ROOT, 'hooks')
    if hooks_dir not in sys.path:
        sys.path.insert(0, hooks_dir)

try:
    from swe_hooks.core.config import (
        load_setup_complete, 
        get_working_memory_filename, read_working_memory_state
    )
    from swe_hooks.core.state_manager import StateManager
except ImportError as e:
    print(json.dumps({"systemMessage": f"SWE import error: {e}"}), file=sys.stdout)
    sys.exit(0)


# Patterns that indicate a continuation of the current task
CONTINUATION_PATTERNS = [
    r'^(yes|yeah|yep|yup|ok|okay|sure|continue|proceed|go ahead|keep going|next|do it)[\s\.\!\?]*$',
    r'^(sounds good|looks good|perfect|great|good|fine|alright)[\s\.\!\?]*$',
    r'^(please continue|please proceed|go on|carry on)[\s\.\!\?]*$',
    r'^(that\'?s? (good|great|fine|correct|right))[\s\.\!\?]*$',
    r'^(approved?|confirmed?|accept(ed)?)[\s\.\!\?]*$',
    r'continue (with )?the',
    r'keep (working|going)',
    r'finish (the|this|it)',
    r'modify (the|this|it)',
    r'add (a|the|this|it)',
    r'complete (the|this|it)',
]

# Patterns that indicate an addition to the current task (not a new task)
ADDITION_PATTERNS = [
    r'^(also|additionally|and also|plus|another thing)',
    r'^(one more thing|by the way|btw)',
    r'^(can you also|could you also|please also)',
    r'^(don\'?t forget|remember to|make sure)',
    r'^(oh and|oh,? also)',
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
    
    # If we're in an active execution state and prompt is short, likely continuation
    active_states = ['WF_EXECUTE', 'WF_CHECKPOINT', 'WF_VERIFY', 'WF_DEBUG_TDD']
    if current_state in active_states and len(prompt_lower) < 50:
        return 'continuation'
    
    # Default: treat as potential new task for safety
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
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "⚠️ SWE not initialized. Run /swe-init first."
                }
            }
            print(json.dumps(output))
            sys.exit(0)
        
        # Extract session ID from transcript_path for session isolation
        transcript_path = input_data.get('transcript_path', '')
        session_id = None
        if transcript_path:
            uuid_match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', transcript_path)
            if uuid_match:
                session_id = uuid_match.group(1)[:8]
        
        # Get current state from WM (session-isolated)
        # Only use working memory if it matches this session
        wm_file = get_working_memory_filename(cwd)
        state_data, _ = read_working_memory_state(cwd)
        
        # Check if the working memory belongs to THIS session
        wm_session_id = None
        if state_data:
            wm_session_id = state_data.get("session_id")

        # If no working memory, OR working memory has no session ID (old format),
        # OR session ID mismatch, start fresh at WF_INIT
        should_reset = (
            not state_data or              # No working memory found
            not wm_session_id or           # WM has no session ID (old format)
            (session_id and session_id != wm_session_id)  # Session mismatch
        )

        if should_reset:
            # No working memory for this session - start at WF_INIT
            current_state = "WF_INIT"
            wm_file = None  # Don't show old session's working memory
        else:
            current_state = state_data.get("current_state", "WF_INIT")
        
        # Create StateManager for potential transitions
        state_mgr = StateManager(cwd)
        
        # Analyze prompt intent
        prompt_intent = analyze_prompt(prompt, current_state)
        
        # Handle WF_INIT state - always direct to WF_INIT workflow
        if current_state == 'WF_INIT':
            context = f"""<workflow-gate state="WF_INIT" session="{session_id or 'unknown'}">
<blocking-instruction priority="CRITICAL">
STOP. Your next action MUST be a tool call. Not text. A tool call.

Call this tool NOW:
mcp__plugin_swe_serena__read_memory("WF_INIT")

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
        if current_state in ['UNINITIALIZED', 'WF_DONE', 'WF_CLEANUP', None]:
            # Check if we have a valid working memory for THIS session
            # If so, this is a "new task in same session" - preserve working memory
            is_same_session_new_task = (
                wm_file and
                wm_session_id and
                session_id and
                wm_session_id == session_id and
                current_state in ['WF_DONE', 'WF_CLEANUP']
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
                context = f"""📋 WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}

MANDATORY: Before responding, read and follow the WF_START workflow.
Use: mcp__serena__read_memory("WF_START")
"""
            else:
                # In active state - continue workflow
                context = f"""➡️ CONTINUING WORKFLOW: {current_state}
Working Memory: {wm_file or 'None'}

Continue with the current workflow step.
If you need to review instructions: mcp__serena__read_memory("{current_state}")
"""
        
        elif prompt_intent == 'addition':
            # User is adding to current task - stay in current state
            context = f"""➕ TASK ADDITION - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}

User is adding to the current task. Incorporate this into your current workflow step.
If scope changes significantly, transition to WF_CLASSIFY.
"""
        
        elif prompt_intent == 'same_session_new_task':
            # New task in same session after WF_DONE - preserve and update existing working memory
            context = f"""🔄 NEW TASK IN SAME SESSION - WORKFLOW STATE: {current_state}
Working Memory: {wm_file}
Session: {session_id}

**IMPORTANT: This is a NEW TASK in the SAME SESSION after completing WF_DONE.**

**DO NOT create a new WM file.** Instead:

1. **UPDATE the existing WM ({wm_file}):**
   - Increment `Task Iteration` counter
   - Move previous task to `## Completed Tasks (This Session)` section
   - Add new task to `## Active Task`
   - Reset `Edit Count Since Checkpoint` to 0
   - Set `Current State` to `WF_CLASSIFY`

2. **Then proceed with task classification:**
   Use: mcp__serena__read_memory("WF_CLASSIFY")
"""

        elif prompt_intent == 'new_task':
            # New task - transition to WF_START
            if current_state not in ['WF_START', 'WF_INIT']:
                state_mgr.transition_to('WF_START')
                current_state = 'WF_START'

            context = f"""🆕 NEW TASK DETECTED - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}

MANDATORY: Before responding, read and follow the {current_state} workflow instructions.
Use: mcp__serena__read_memory("{current_state}")
"""
        
        else:
            # Unknown intent - route to WF_CLASSIFY for proper classification
            if current_state == 'WF_START':
                context = f"""❓ INTENT UNCLEAR - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}

MANDATORY: Before responding, read and follow WF_START to initialize.
Then proceed to WF_CLASSIFY for task classification.
Use: mcp__serena__read_memory("{current_state}")
"""
            else:
                # Transition to WF_CLASSIFY for classification
                state_mgr.transition_to('WF_CLASSIFY')
                context = f"""❓ INTENT UNCLEAR - Routing to WF_CLASSIFY
Working Memory: {wm_file or 'None'}

MANDATORY: Classify this task using WF_CLASSIFY.
Use: mcp__serena__read_memory("WF_CLASSIFY")
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
