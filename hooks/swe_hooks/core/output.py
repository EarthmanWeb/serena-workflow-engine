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
"""

import json
import sys
from typing import Optional, Dict, Any


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
