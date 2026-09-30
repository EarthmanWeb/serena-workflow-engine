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
import time
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.config import (
        load_setup_complete,
        get_working_memory_filename, read_working_memory_state,
        read_state_file, write_state_file,
    )
    from swe_hooks.core.session import extract_session_id, find_working_memory_for_session, get_project_root
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import (
        get_stream_path, get_event_count, get_sentinel_path, append_event,
        append_task_boundary,
    )
    from swe_hooks.core.output import emit_once, WF_INIT_GUIDANCE
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "UserPromptSubmit")


def create_wm_and_sentinel(cwd, session_id, initial_state='WF_CLASSIFY',
                           prev_state='WF_INIT', task='(awaiting classification)',
                           stamp_session_start=True):
    """Create the Working Memory markdown, state file, init sentinel, and
    session_start stream event when a session first enters WF_CLASSIFY.

    Ported from the block that previously lived in swe_post_read_state.py
    (where it ran on transition to the old post-init entry state, now removed).
    WF_CLASSIFY is the new post-init entry state in v4.

    `initial_state`/`prev_state`/`task` are parameterized so the fast-track
    path can create the WM directly at WF_EXECUTE. Defaults preserve the
    standard WF_CLASSIFY entry for all existing callers.

    `stamp_session_start=False` re-creates the WM WITHOUT advancing the task
    boundary: 'session_start' is a boundary in events_since_task_start(), so
    a mid-session re-invocation (slash-command fast track) must not stamp it —
    the in-flight task's docreads must keep counting toward sweep verification.
    """
    project_root = get_project_root()
    wm_filename = f"WM_{session_id}.md"
    wm_filepath = os.path.join(project_root, ".serena", "memories", wm_filename)

    wm_content = f"""# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: {task}
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Workflow Context
**Current State**: {initial_state}
**Previous State**: {prev_state}
**Session ID**: {session_id}

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

    # Write initial decoupled state file
    write_state_file(session_id, initial_state, prev_state=prev_state)

    # Session-start stream event = task boundary; skipped on mid-session
    # WM re-creation so the in-flight task's docreads keep counting.
    if stamp_session_start:
        append_event(get_stream_path(session_id), 'session_start', s=session_id)

    # Create init sentinel — unlocks the pre-init gate for this session
    sentinel = get_sentinel_path(session_id)
    try:
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        sentinel_data = {
            "session_id": session_id,
            "wm_file": wm_filename.replace('.md', ''),
            "validated_at": int(time.time()),
        }
        with open(sentinel, 'w') as sf:
            json.dump(sentinel_data, sf, separators=(',', ':'))
    except IOError:
        pass

    return wm_filename.replace('.md', '')


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

# Unambiguous new-task openers: phrasing that only makes sense as a pivot to
# fresh work, regardless of what task is in flight.
NEW_TASK_PATTERNS = [
    r'^(new task|different task|change of plans|something else|switch to)',
    r'^(forget (that|the previous)|start over|start fresh|reset)',
    r'^(i want to|let\'?s? (work on|do|start))',
    r'^(help me (with|build|create|implement|add|fix|debug|review))',
    r'^(can you help|i need help|i need you to)',
]

# Bare imperative verbs. A leading "fix …" / "add …" is a pivot ONLY at the
# start of work OR when paired with a pivot cue below — otherwise mid-task
# "fix the spacing too" / "add a border" is feedback on the CURRENT task, not
# a new one. analyze_prompt() gates these behind NEW_TASK_CUE_RE.
BARE_VERB_TASK_PATTERNS = [
    r'^(create|build|implement|add|fix|debug|review|analyze|refactor)\b',
    r'^(onboard|write|develop|make|design|setup|configure|install)\b',
]

# Cue that a bare-verb prompt is a genuine pivot rather than a refinement of
# the current task. Presence of any of these upgrades a bare verb to new_task.
NEW_TASK_CUE_RE = re.compile(
    r'\b(instead|now|next|new (task|feature|thing|issue|bug)|'
    r'switch(ing)? to|different|another (task|feature|issue|bug|thing)|'
    r'unrelated|separate(ly)?|forget (that|this|the)|start over)\b',
    re.IGNORECASE,
)


# A WF_RESEARCH-specific escape hatch. Research is read-only exploration; once
# findings are in, the user asking for the work to actually be done ("do
# everything", "implement it", "fix it", "go ahead") is the DECLARED
# needs_implementation transition into WF_CLASSIFY — not a pivot the model has
# to weigh against feedback (pivot_analysis_note's framing). Word-boundary,
# case-insensitive; matches an imperative to implement/apply/proceed with the
# researched work, including a bare pronoun object ("do it/that/this/
# everything/all of it").
RESEARCH_IMPLEMENT_RE = re.compile(
    r'\b(implement|do (it|that|this|everything|all of it)|go ahead|fix|add|'
    r'change|update|apply|build|proceed|'
    r'make (the|those|these) changes)\b',
    re.IGNORECASE,
)


# Deploy/push/ship intent in a prompt: inject the docs-first pre-deploy gate
# INTO the turn's context, at the decision point. Reading git/package.json to
# "figure out the pipeline" instead of the deploy memories is the canonical
# violation this prevents.
DEPLOY_INTENT_RE = re.compile(
    r'\b(deploy|push (it|this|live)|ship (it|this)|go(es)? live|release (it|this|the))\b',
    re.IGNORECASE,
)

PRE_DEPLOY_NOTE = """🚀 PRE-DEPLOY GATE (docs first — mechanically enforced):
LITERAL FIRST tool calls for a deploy/push/ship request are MEMORY reads, in this order:
  1. mcp__plugin_swe_serena__search_memories_by_name("deploy") → read every deploy
     memory for this project (pipeline, commands, permission rules)
  2. Only THEN identify what changed and run the DOCUMENTED pipeline in its order.
Reading git status/diff/log, package.json, or .github/workflows/ to reverse-engineer
the pipeline BEFORE the deploy memories is the forbidden improvisation — the
docs-first gate will deny those calls until a memory is consulted this turn.
Push and deploy each require explicit operator permission THIS session.

"""


def deploy_note_for(prompt: str) -> str:
    """Return the pre-deploy context block for deploy-intent prompts, else ''."""
    return PRE_DEPLOY_NOTE if DEPLOY_INTENT_RE.search(prompt or '') else ''


def pivot_analysis_note(current_state: str, wm_file: str, stream_info: str,
                        cue_hint: bool, session_id: str = None) -> str:
    """Instruction for an ACTIVE state when intent is ambiguous.

    The deterministic hook cannot read meaning, so it does NOT force a
    transition. It stays in the current state and asks the MODEL — which has
    full conversation context — to decide pivot vs. feedback and self-transition
    on a genuine pivot only. Keyword cues are passed as a HINT, never as the
    decision.
    """
    hint_line = (
        "\nA new-task cue word was present, but that ALONE is not decisive — "
        "weigh it against the actual conversation.\n" if cue_hint else "\n")
    sid = session_id or "<id>"
    return f"""➡️ CURRENT STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

Ambiguous intent — the workflow hook did NOT transition. Decide from the FULL
conversation, not this message alone:
{hint_line}
  • Feedback, correction, refinement, or a follow-up on the CURRENT task
    (even phrased as "fix …" / "add …" / "no, do it differently") →
    STAY in {current_state} and apply it. Do NOT re-classify.
  • A genuine BRAND-NEW task or COMPLETE pivot (different feature/subject with
    no dependency on the work in flight) → call
    mcp__plugin_swe_swe-wm__swe_wm_transition(session_id="{sid}",
    target_state="WF_CLASSIFY", reason="pivot") yourself, then classify.

Default to STAY when uncertain — re-classifying mid-task is the costly error.
Review the current step if needed: mcp__plugin_swe_serena__read_memory(memory_name="wf/{current_state}")
"""


def research_exit_directive(session_id: str, wm_file: str, stream_info: str) -> str:
    """Directive for WF_RESEARCH when the prompt asks for the researched work
    to actually be implemented.

    Unlike pivot_analysis_note, this is NOT an ambiguous-intent judgment call —
    it is the DECLARED needs_implementation transition out of research into
    WF_CLASSIFY. The hook does not auto-transition (directive only): the
    primary action is reading wf/WF_CLASSIFY, which readAdvance now allows to
    advance WF_RESEARCH -> WF_CLASSIFY directly. If that read reports
    "inspecting — no transition" (readAdvance not wired for this edge), the
    explicit swe_wm_transition MCP tool call is the fallback, with the
    set_state.py CLI as a last resort.
    """
    sid = session_id or "<id>"
    return f"""➡️ CURRENT STATE: WF_RESEARCH
Working Memory: {wm_file or 'None'}{stream_info}

DECLARED TRANSITION: needs_implementation (WF_RESEARCH → WF_CLASSIFY).
This is not a pivot judgment call — the prompt asked for the researched work
to actually be done. Findings are complete; move to classification and
execution:

1. PRIMARY: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_CLASSIFY")
   — readAdvance now carries WF_RESEARCH → WF_CLASSIFY forward on this read.
2. If that read reports "inspecting — no transition" (no forward edge fired),
   call mcp__plugin_swe_swe-wm__swe_wm_transition(session_id="{sid}",
   target_state="WF_CLASSIFY", reason="needs_implementation") explicitly.
3. CLI fallback if the MCP tool is unavailable:
   python3 "${{CLAUDE_PLUGIN_ROOT}}/hooks/swe_hooks/tools/set_state.py" {sid} WF_CLASSIFY
"""


# A direct slash-command invocation. The harness wraps command runs in a
# <command-name>/foo</command-name> marker; bare prompts that the user types as
# "/foo ..." also count. Either way the tool/command fully encodes intent — no
# classification is needed, so we fast-track straight to WF_EXECUTE.
COMMAND_MARKER_RE = re.compile(r'<command-name>\s*(/?[^<\s]+)', re.IGNORECASE)
SLASH_COMMAND_RE = re.compile(r'^/[a-zA-Z0-9][\w:-]*')


# A background-task/agent-completion notification, not genuine user input.
# These land in the transcript as a "user" turn (the harness's delivery
# mechanism) but carry no task intent to classify — routing them through
# WF_CLASSIFY / "INTENT UNCLEAR" produces pure noise on every subagent or
# background-Bash completion. Matches:
#   - the <task-notification> wrapper tag
#   - a prompt starting with "[SYSTEM NOTIFICATION"
#   - `Agent "<name>" finished` (the Agent-tool completion phrasing)
BACKGROUND_NOTIFICATION_RE = re.compile(
    r'<task-notification>|^\s*\[SYSTEM NOTIFICATION|Agent\s+"[^"]*"\s+finished',
    re.IGNORECASE,
)


def is_background_notification(prompt: str) -> bool:
    """True when `prompt` is a background task/agent-completion notification
    rather than genuine user input requiring classification."""
    return bool(BACKGROUND_NOTIFICATION_RE.search(prompt or ''))


def detect_slash_command(prompt: str):
    """Return the invoked command token (e.g. '/gherkin-dev') for a direct
    slash-command prompt, else None.

    Recognizes both the harness <command-name> marker and a bare prompt that
    starts with '/<token>'.
    """
    if not prompt:
        return None
    marker = COMMAND_MARKER_RE.search(prompt)
    if marker:
        token = marker.group(1)
        return token if token.startswith('/') else '/' + token
    stripped = prompt.lstrip()
    m = SLASH_COMMAND_RE.match(stripped)
    if m:
        return m.group(0)
    return None


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
    
    # Unambiguous new-task openers always pivot.
    for pattern in NEW_TASK_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            return 'new_task'

    # Bare imperative verbs ("fix …", "add …"):
    #   - No task in flight yet → classify normally (it IS the task).
    #   - Mid-task → NOT decided by verbiage alone. A cue ("instead", "now",
    #     "new task", …) or a bare verb are only HINTS; the real pivot-vs-
    #     feedback call needs full conversation context, which this
    #     deterministic hook does not have. Return 'possible_pivot' so the
    #     caller keeps the current state and asks the MODEL to analyze and
    #     self-transition only on a genuine pivot.
    for pattern in BARE_VERB_TASK_PATTERNS:
        if re.search(pattern, prompt_lower, re.IGNORECASE):
            not_in_active_task = current_state in ('WF_CLASSIFY', 'WF_INIT',
                                                   'UNINITIALIZED', 'WF_DONE', None)
            if not_in_active_task:
                return 'new_task'
            return 'possible_pivot'

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

        prompt_lower = prompt.lower().strip()

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

        # Background task / agent-completion notification: not genuine user
        # intent, so no classification, no transition, no boundary stamp.
        # Emit nothing (or a minimal no-op context) rather than routing it
        # through the unknown-intent / WF_CLASSIFY noise path.
        #
        # Gated on an EXISTING state file/WM for this session: on the
        # session's genuine FIRST prompt there is no prior init to route
        # around, so a first prompt that happens to quote/paste text
        # matching this pattern (e.g. a bug report containing
        # "[SYSTEM NOTIFICATION]" or an "Agent \"x\" finished" transcript
        # snippet) must NOT be swallowed before WM/session setup ever runs —
        # it needs the normal WF_INIT/WF_CLASSIFY path like any other first
        # message. Only a session that has ALREADY initialized can have a
        # genuine background-notification turn land mid-session.
        if session_id and read_state_file(session_id) and is_background_notification(prompt):
            print(json.dumps({}))
            sys.exit(0)

        # Turn marker for per-turn gates (e.g. the docs-first search gate
        # counts 'docread' events since the last 'prompt' marker).
        if session_id:
            append_event(get_stream_path(session_id), 'prompt', s=session_id)

        # ═══ FAST TRACK: direct slash-command invocation ═══
        # A slash command fully encodes intent — there is nothing to classify.
        # Create the WM + sentinel directly at WF_EXECUTE so the init gate opens
        # immediately and the command/skill runs with full abilities. The only
        # behavioral constraint we still carry is CLAUDE_OBLIGATIONS.
        # Applies on ANY slash command, fresh or mid-session (state is forced
        # to WF_EXECUTE; an existing WM is overwritten for this session).
        command = detect_slash_command(prompt)
        if command and session_id:
            # Mid-session re-invocation keeps the current task boundary:
            # stamping 'session_start' again would drop the task's docreads
            # from sweep verification (an unwinnable re-read loop when the
            # command IS /swe-wm-update). Only a session with no state file
            # yet gets the boundary stamp.
            create_wm_and_sentinel(
                cwd, session_id,
                initial_state='WF_EXECUTE',
                prev_state='WF_FASTTRACK',
                task=f'Direct command: {command}',
                stamp_session_start=not read_state_file(session_id),
            )
            context = f"""⚡ FAST TRACK — direct command: {command}
Working Memory: WM_{session_id} (state: WF_EXECUTE)

This is a direct slash-command/skill invocation. The command encodes all intent —
NO classification, NO WF_INIT chain, NO WF_CLASSIFY. Fast-tracked to WF_EXECUTE.

1. Read behavioral constraints once: mcp__plugin_swe_serena__read_memory(memory_name="claude/CLAUDE_OBLIGATIONS")
2. Then execute {command} exactly as invoked, with all the abilities that command provides.
"""
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context
                }
            }
            print(json.dumps(output))
            sys.exit(0)

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
        
        # Handle WF_INIT state - always direct to WF_INIT workflow.
        # E2: the full blocking block goes through emit_once — when the
        # SessionStart banner (or an earlier WF_INIT prompt) already carried
        # identical guidance this session, inject a ONE-LINE reminder instead
        # of a duplicate block.
        if current_state == 'WF_INIT':
            if emit_once(session_id, WF_INIT_GUIDANCE):
                context = deploy_note_for(prompt) + f"""<workflow-gate state="WF_INIT" session="{session_id or 'unknown'}">
<blocking-instruction priority="CRITICAL">
{WF_INIT_GUIDANCE}
</blocking-instruction>
</workflow-gate>"""
            else:
                context = deploy_note_for(prompt) + (
                    f"⛔ WF_INIT (session {session_id or 'unknown'}): next "
                    "action is the tool call mcp__plugin_swe_serena__"
                    'read_memory(memory_name="wf/WF_INIT") — full guidance '
                    "already shown this session.")
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
                success, _ = state_mgr.transition_to('WF_CLASSIFY')
                if success and session_id:
                    # Genuine new task: stamp the boundary so the sweep is
                    # verified against THIS task's reads only.
                    append_task_boundary(
                        get_stream_path(session_id), current_state, session_id)
                current_state = 'WF_CLASSIFY'
                # Analyze the prompt to understand intent (don't force new_task)
                prompt_intent = analyze_prompt(prompt, current_state)
                if prompt_intent == 'unknown':
                    prompt_intent = 'same_session_new_task'  # Special case
            else:
                # Truly new session or no working memory - go to WF_CLASSIFY
                state_mgr.transition_to('WF_CLASSIFY')
                current_state = 'WF_CLASSIFY'
                # No WM exists for this session yet — create it now (its
                # session_start event is the task boundary).
                if not wm_file:
                    wm_file = create_wm_and_sentinel(cwd, session_id)
                prompt_intent = 'new_task'
        
        # Build context based on prompt intent and state
        if prompt_intent == 'continuation':
            # User is continuing - stay in current state, provide brief reminder
            if current_state == 'WF_CLASSIFY':
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

MANDATORY: Before responding, read and follow the WF_CLASSIFY workflow.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_CLASSIFY")
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
                if current_state == 'WF_RESEARCH' and RESEARCH_IMPLEMENT_RE.search(prompt_lower):
                    context = research_exit_directive(session_id, wm_file, stream_info)
                else:
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
            if current_state == 'WF_RESEARCH' and RESEARCH_IMPLEMENT_RE.search(prompt_lower):
                context = research_exit_directive(session_id, wm_file, stream_info)
            else:
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
            # New task - transition to WF_CLASSIFY
            if current_state not in ['WF_CLASSIFY', 'WF_INIT']:
                success, _ = state_mgr.transition_to('WF_CLASSIFY')
                if success and session_id:
                    # Genuine new task: stamp the boundary. Continuation /
                    # unclear prompts never stamp — they must not invalidate
                    # the in-flight task's docreads for sweep verification.
                    append_task_boundary(
                        get_stream_path(session_id), current_state, session_id)
                current_state = 'WF_CLASSIFY'
                if not wm_file:
                    wm_file = create_wm_and_sentinel(cwd, session_id)

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
        
        elif prompt_intent == 'possible_pivot':
            # A bare-verb prompt ("fix …", "add …") mid-task. Could be a pivot,
            # could be feedback. NOT decided by verbiage here — stay in the
            # current state and let the model analyze the full conversation,
            # self-transitioning via /swe-goto WF_CLASSIFY only on a true pivot.
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            if current_state == 'WF_RESEARCH' and RESEARCH_IMPLEMENT_RE.search(prompt_lower):
                context = research_exit_directive(session_id, wm_file, stream_info)
            else:
                cue_hint = bool(NEW_TASK_CUE_RE.search(prompt_lower))
                context = pivot_analysis_note(current_state, wm_file, stream_info,
                                              cue_hint, session_id=session_id)

        else:
            # Unknown intent. Only a VERIFIED pivot (an explicit new_task
            # pattern) re-classifies — that path is handled above. Here the
            # intent is genuinely unclear, which for an in-flight task is
            # overwhelmingly mid-task feedback ("that didn't work", "no, use
            # X instead", "the button is still off"). Re-classifying on every
            # such message was the "too strict" bug: it dragged the model back
            # through WF_CLASSIFY on ordinary feedback, and from WF_EXECUTE the
            # WF_CLASSIFY transition is not even a valid matrix edge.
            #
            # Rule: unknown intent STAYS in the current state. A brand-new task
            # or complete pivot is judged by the MODEL from full context (it can
            # self-transition via /swe-goto WF_CLASSIFY) — not force-decided by
            # this deterministic hook.
            # Get stream event count for observability
            stream_info = ""
            if session_id:
                stream_path = get_stream_path(session_id)
                event_count = get_event_count(stream_path)
                if event_count > 0:
                    stream_info = f"\nStream Events: {event_count}"
            if current_state in ('WF_CLASSIFY', 'WF_INIT'):
                # Not yet classified — genuinely need to classify.
                context = f"""❓ INTENT UNCLEAR - WORKFLOW STATE: {current_state}
Working Memory: {wm_file or 'None'}{stream_info}

MANDATORY: Classify this task using WF_CLASSIFY.
Use: mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_CLASSIFY")
"""
            elif current_state == 'WF_RESEARCH' and RESEARCH_IMPLEMENT_RE.search(prompt_lower):
                context = research_exit_directive(session_id, wm_file, stream_info)
            else:
                # Active task state — stay put and let the model judge pivot vs.
                # feedback from full context (no verbiage-only decision).
                context = pivot_analysis_note(current_state, wm_file,
                                              stream_info, cue_hint=False,
                                              session_id=session_id)
        
        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": deploy_note_for(prompt) + context
            }
        }
        print(json.dumps(output))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"systemMessage": f"Workflow hook error: {e}"}), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
