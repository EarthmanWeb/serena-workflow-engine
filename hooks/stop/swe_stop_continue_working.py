#!/usr/bin/env python3
"""Stop hook - Workflow check + prevent unnecessary pauses.

Combines two responsibilities:
  1. Workflow state check: logs interruption to stream when stopping in incomplete state
  2. Continue-working: blocks Claude from stopping unnecessarily

Blocks Claude from stopping when:
  - Response was cut off by token limit (max_tokens) — always continues
  - Claude is asking for unnecessary confirmation to proceed — continues
  - Claude is presenting implementation options instead of choosing — continues
  - Workflow is in an incomplete state (WF_EXECUTE, WF_VERIFY, etc.) — continues

Allows Claude to stop when:
  - Task is genuinely complete (WF_DONE)
  - Session is uninitialized
  - Genuine user input is needed (requirements, business logic)
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.output import output_empty
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import get_stream_path, append_event
    from swe_hooks.core.session import extract_session_id
    from swe_hooks.core.config import read_state_file, write_state_file
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "Stop")

# Workflow states where active work is in progress — should block stopping
INCOMPLETE_STATES = {
    'WF_EXECUTE', 'WF_DEBUG_TDD', 'WF_ARCH_REVIEW',
    'WF_CHECKPOINT', 'WF_SWARM_ORCHESTRATE'
}

# Workflow states where stopping is fine (completion states + uninitialized)
# WF_VERIFY is allowed to stop — continuation directives guide transition to WF_DONE
ALLOW_STOP_STATES = {'WF_DONE', 'WF_VERIFY', 'UNINITIALIZED', ''}

# Max consecutive stop blocks in same state before allowing (escape hatch)
# Inspired by IronBee's retry-limited verify-gate pattern
MAX_STOP_RETRIES = 3

# Patterns that indicate Claude is asking unnecessary permission to continue
CONTINUE_PATTERNS = re.compile(
    r'(?:shall I (?:continue|proceed|go ahead|move on|start|begin)|'
    r'would you like me to (?:continue|proceed|go ahead|move on|start|begin|implement|make)|'
    r'should I (?:continue|proceed|go ahead|move on|start|begin|implement|make)|'
    r'ready to (?:proceed|continue|move on)|'
    r'want me to (?:continue|proceed|start|begin|implement|make|go ahead)|'
    r'do you want me to (?:continue|proceed|go ahead)|'
    r'let me know (?:if|when|how) you.*(?:want|like|ready|prefer)|'
    r'before I (?:proceed|continue|start|begin|go ahead)|'
    r'waiting for (?:your|you)|'
    r'need your (?:approval|confirmation|go.ahead)|'
    r'(?:approve|confirm) (?:this|the)|'
    r'give me the (?:go.ahead|green light))',
    re.IGNORECASE
)

# Patterns that indicate Claude is presenting options instead of choosing
OPTIONS_PATTERNS = re.compile(
    r'(?:which (?:option|approach|method|way|solution) (?:do you|would you|should)|'
    r'option [0-9].*option [0-9].*which|'
    r'prefer (?:option|approach) [A-Z0-9]|'
    r'choose between)',
    re.IGNORECASE
)

# Patterns that indicate genuine user-facing questions (should NOT block)
# Covers: requirement clarification, destructive operations, approach choices,
# trade-off questions, file/data deletion, and any question needing real user input
GENUINE_INPUT_PATTERNS = re.compile(
    r'(?:requirement|specification|business logic|'
    r'user.*(?:want|need|expect)|'
    r'stakeholder|product (?:owner|manager)|'
    r'which (?:database|api|service|endpoint|approach|option|method|strategy)|'
    r'what (?:format|schema|structure|approach|behavior) (?:should|do you|would you)|'
    r'(?:delet|remov|drop|destroy|overwrite|discard|reset|revert)(?:e|ing)?.*\?|'
    r'(?:safe|okay|acceptable|appropriate) to (?:delete|remove|drop|overwrite|reset)|'
    r'(?:break|breaking) change|'
    r'trade.?off|downside|risk|concern|'
    r'(?:prefer|rather|instead|better|worse)|'
    r'how (?:should|would you like|do you want)|'
    r'(?:which|what) (?:one|way|direction|path)|'
    r'are you sure|do you (?:want|confirm|agree)|'
    r'is (?:that|this) (?:okay|acceptable|correct|right|what you))',
    re.IGNORECASE
)


def count_stop_blocks(stream_path: str, current_state: str) -> int:
    """Count consecutive stop_blocked events in the same state from end of stream.

    Resets when state changes or a non-stop-block event occurs.
    """
    if not os.path.exists(stream_path):
        return 0
    try:
        file_size = os.path.getsize(stream_path)
        with open(stream_path, 'r') as f:
            if file_size > 10240:
                f.seek(max(0, file_size - 10240))
                f.readline()
            lines = f.readlines()

        count = 0
        for line in reversed(lines):
            try:
                event = json.loads(line.strip())
                if (event.get('type') == 'stop_blocked' and
                        event.get('state') == current_state):
                    count += 1
                else:
                    break
            except (json.JSONDecodeError, ValueError):
                continue
        return count
    except IOError:
        return 0


def block_stop(reason: str):
    """Output a Stop-blocking response. Uses top-level decision/reason."""
    result = {
        "decision": "block",
        "reason": reason
    }
    print(json.dumps(result), file=sys.stdout)
    sys.exit(0)


def extract_last_assistant_text(transcript_path: str) -> str:
    """Extract the last assistant text message from the transcript."""
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""

    try:
        last_text = ""
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get('type') == 'assistant':
                        content = entry.get('message', {}).get('content', [])
                        for block in content:
                            if isinstance(block, dict) and block.get('type') == 'text':
                                last_text = block.get('text', '')
                except json.JSONDecodeError:
                    continue
        return last_text
    except Exception:
        return ""



def _persist_state_on_stop(session_id: str, current_state: str):
    """Persist current state to JSON state file at end of response.

    This is the stop-hook anchoring pattern: state is saved at message
    boundaries so the prompt hook can recover context on the next message.
    """
    if not session_id:
        return
    try:
        existing = read_state_file(session_id)
        if existing:
            # Touch the timestamp to mark last activity
            write_state_file(
                session_id,
                current_state,
                prev_state=existing.get('prev_state'),
                task=existing.get('task'),
                features=existing.get('features'),
                progress=existing.get('progress'),
            )
    except Exception:
        pass  # Best-effort, never block stop

def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        stop_reason = get_input_field(input_data, 'stop_reason', default='unknown')
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        # --- Resolve workflow state ---
        session_id = extract_session_id(transcript_path)
        try:
            state_mgr = StateManager(cwd, session_id=session_id)
            current_state = state_mgr.get_current_state()
        except Exception:
            current_state = ''

        # WF_DONE or uninitialized — always allow stop
        if current_state in ALLOW_STOP_STATES:
            _persist_state_on_stop(session_id, current_state)
            output_empty()
            return

        # --- Case 1: Token limit hit — ALWAYS continue ---
        if stop_reason == 'max_tokens':
            # Log interruption to stream
            if session_id:
                try:
                    stream_path = get_stream_path(session_id)
                    append_event(stream_path, 'interrupted',
                                 state=current_state, s=session_id,
                                 reason='max_tokens')
                except Exception:
                    pass

            block_stop(
                "Your response was cut off by the token limit. "
                "Continue from where you left off. Do not repeat what you "
                "already said — pick up exactly where you stopped."
            )
            return

        # --- Case 2: Incomplete workflow state — block + log ---
        if current_state in INCOMPLETE_STATES:
            # Log interruption to stream
            if session_id:
                try:
                    stream_path = get_stream_path(session_id)
                    append_event(stream_path, 'interrupted',
                                 state=current_state, s=session_id,
                                 reason='end_turn')
                except Exception:
                    pass

            # Check transcript for WHY Claude stopped
            last_msg = extract_last_assistant_text(transcript_path)

            # Check retry count — escape hatch after MAX_STOP_RETRIES
            stream_path = get_stream_path(session_id) if session_id else None
            if stream_path:
                retry_count = count_stop_blocks(stream_path, current_state)
                if retry_count >= MAX_STOP_RETRIES:
                    # Escape hatch: allow stop after too many blocks
                    append_event(stream_path, 'stop_escaped',
                                 state=current_state, s=session_id,
                                 retries=retry_count)
                    result = {
                        "stopReason": (
                            f"⚠️ Stop allowed after {retry_count} blocks in {current_state}. "
                            f"Claude may be genuinely stuck. Review the situation."
                        )
                    }
                    print(json.dumps(result), file=sys.stdout)
                    sys.exit(0)
                    return

            # If asking unnecessary confirmation — check if it's a genuine question first
            if last_msg and CONTINUE_PATTERNS.search(last_msg):
                # Genuine questions (deletions, trade-offs, approach choices) must reach the user
                if GENUINE_INPUT_PATTERNS.search(last_msg):
                    _persist_state_on_stop(session_id, current_state)
                    output_empty()
                    return
                if stream_path:
                    append_event(stream_path, 'stop_blocked',
                                 state=current_state, s=session_id,
                                 reason='confirmation_pattern')
                block_stop(
                    f"Workflow is in {current_state} — work is not complete. "
                    "Continue with the next step."
                )
                return

            # If presenting options instead of choosing — block
            if last_msg and OPTIONS_PATTERNS.search(last_msg):
                if not GENUINE_INPUT_PATTERNS.search(last_msg):
                    if stream_path:
                        append_event(stream_path, 'stop_blocked',
                                     state=current_state, s=session_id,
                                     reason='options_pattern')
                    block_stop(
                        f"Workflow is in {current_state} — work is not complete. "
                        "Pick the best approach based on existing patterns and "
                        "implement it. Use your judgment."
                    )
                    return

            # Incomplete state but Claude isn't asking confirmation —
            # still warn but allow stop (might be genuinely stuck)
            _persist_state_on_stop(session_id, current_state)
            result = {
                "stopReason": f"⚠️ Stopping with incomplete work: {current_state}"
            }
            print(json.dumps(result), file=sys.stdout)
            sys.exit(0)
            return

        # --- Case 3: Other states (WF_CLASSIFY, etc.) ---
        # In non-incomplete states, allow stops so the user can respond.
        # Only block if it's a pure workflow-navigation pause (not a real question).
        if stop_reason == 'end_turn':
            last_msg = extract_last_assistant_text(transcript_path)
            if last_msg and CONTINUE_PATTERNS.search(last_msg):
                # Always allow stop here — the user should be able to answer
                _persist_state_on_stop(session_id, current_state)
                output_empty()
                return

        # --- Default: Allow the stop ---
        _persist_state_on_stop(session_id, current_state)
        output_empty()

    except Exception:
        # On error, allow the stop (don't trap Claude)
        output_empty()


if __name__ == '__main__':
    main()
