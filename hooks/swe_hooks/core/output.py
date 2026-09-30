"""Hook output helpers following official Claude Code hooks reference.

See: https://code.claude.com/docs/en/hooks

Output goes to STDOUT as JSON. Exit is ALWAYS 0.

For messages (all events):
  - Use hookSpecificOutput.additionalContext for context injection

For blocking PreToolUse:
  - Use hookSpecificOutput.permissionDecision = "deny"
  - Use hookSpecificOutput.permissionDecisionReason for deny reason (shown to Claude)
  - Use hookSpecificOutput.additionalContext for extra context (shown before tool executes)

For blocking Stop/SubagentStop/PostToolUse/UserPromptSubmit:
  - Use top-level decision = "block" and reason = "..."

Injection budget (E3): hook-injected context targets ≤2 attachment blocks per
tool call and ≤150k chars per session. Hooks that repeat guidance MUST route
the repeatable block through emit_once() (byte-identical suppression) so a
message is charged to the budget once, not per tool call.
"""

import hashlib
import json
import os
import sys
from typing import Optional, Dict, Any


# Canonical WF_INIT guidance. The SessionStart banner and the UserPromptSubmit
# WF_INIT gate both register/check THIS exact text via emit_once(), so the
# full block is injected once per session — later prompts in WF_INIT get a
# one-line reminder instead of a duplicate block.
WF_INIT_GUIDANCE = """STOP. Your next action MUST be a tool call. Not text. A tool call.

If the tool is deferred, load its schema first (e.g. via ToolSearch when
available), then call mcp__plugin_swe_serena__read_memory(...):

  mcp__plugin_swe_serena__read_memory(memory_name="wf/WF_INIT")

ALWAYS use the fully-qualified name mcp__plugin_swe_serena__read_memory — NEVER
the bare read_memory.

- Do NOT output any text before these tool calls
- Do NOT explain what you're doing
- Do NOT acknowledge the user's message first
- Do NOT skip this because the user asked something specific
- The user's request will be handled AFTER you read WF_INIT

If your next output contains ANY text instead of a tool call, you have failed."""


def emit_once(session_id: str, text: str, streams_dir: str = None) -> bool:
    """Byte-identical suppression (E2): return True when `text` has NOT been
    emitted this session (and record it), False when it already was.

    One sha256 hash per line in .serena/streams/.emitted_<session_id>.
    Fail-open: no session id, or ANY IO error reading/writing the ledger,
    returns True — a message is never lost to the dedupe.
    """
    if not session_id or not text:
        return True
    try:
        if streams_dir is None:
            from swe_hooks.core.stream import get_stream_dir
            streams_dir = get_stream_dir()
        digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
        path = os.path.join(streams_dir, f'.emitted_{session_id}')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip() == digest:
                        return False
        except FileNotFoundError:
            pass
        os.makedirs(streams_dir, exist_ok=True)
        with open(path, 'a', encoding='utf-8') as f:
            f.write(digest + '\n')
        return True
    except OSError:
        return True


class HookOutput:
    """Builds and outputs hook responses in official format."""

    def __init__(self, event_name: str = "PostToolUse"):
        """Initialize with hook event name for proper formatting."""
        self.messages: list[str] = []
        self.should_block = False
        self.block_reason: Optional[str] = None
        self.event_name = event_name

    def add_message(self, msg: str):
        """Add a message to show the user."""
        self.messages.append(msg)

    def block(self, reason: str):
        """Mark operation as blocked (PreToolUse only)."""
        self.should_block = True
        self.block_reason = reason
        self.event_name = "PreToolUse"
        self.add_message(reason)

    def build(self) -> Dict[str, Any]:
        """Build the output dictionary using proper hookSpecificOutput format."""
        if not self.messages and not self.should_block:
            return {}

        result = {
            "hookSpecificOutput": {
                "hookEventName": self.event_name
            }
        }

        if self.should_block:
            result["hookSpecificOutput"]["permissionDecision"] = "deny"
            if self.block_reason:
                result["hookSpecificOutput"]["permissionDecisionReason"] = self.block_reason
        elif self.messages:
            result["hookSpecificOutput"]["additionalContext"] = "\n".join(self.messages)

        return result

    def output_and_exit(self):
        """Output JSON to stdout and exit 0."""
        result = self.build()
        print(json.dumps(result), file=sys.stdout)
        sys.exit(0)


def output_message(msg: str, event: str = "PostToolUse"):
    """Quick helper to output a simple message."""
    result = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": msg
        }
    }
    print(json.dumps(result), file=sys.stdout)
    sys.exit(0)


def output_block(reason: str):
    """Quick helper to block an operation (PreToolUse only)."""
    result = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason
        }
    }
    print(json.dumps(result), file=sys.stdout)
    sys.exit(0)


def output_empty():
    """Output empty result (allow operation silently)."""
    print(json.dumps({}), file=sys.stdout)
    sys.exit(0)


def output_allow_with_input(updated_input: Dict[str, Any], context: Optional[str] = None):
    """Allow a PreToolUse call but replace its tool input (auto-repair).

    Uses permissionDecision="allow" + updatedInput so the harness runs the
    corrected command in place of the one the model sent. Optional context is
    surfaced to the model so it sees what was rewritten.
    """
    hook_out: Dict[str, Any] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": updated_input,
    }
    if context:
        hook_out["permissionDecisionReason"] = context
    print(json.dumps({"hookSpecificOutput": hook_out}), file=sys.stdout)
    sys.exit(0)


def output_status(status: str, event: str = "PostToolUse"):
    """Output a concise one-line status message.

    Use this instead of output_empty() when you want to inform
    the user what happened without being verbose.

    Examples:
        output_status("WM: edit #3 tracked")
        output_status("WM: state unchanged")
        output_status("✓ transition logged")
    """
    result = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": status
        }
    }
    print(json.dumps(result), file=sys.stdout)
    sys.exit(0)


def output_error(error: str, event: str = "PostToolUse"):
    """Output error as message (non-blocking)."""
    result = {
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": f"SWE Hook Error: {error}"
        }
    }
    print(json.dumps(result), file=sys.stdout)
    sys.exit(0)
