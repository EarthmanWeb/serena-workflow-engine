"""Pure helpers for detecting mid-turn user input in a transcript.

Shared by the two Stop hooks (swe_stop_continue_working.py,
swe_stop_response_format.py) so neither one forces an extra turn when the
user has ALREADY typed a follow-up message before the current turn's Stop
event fires. Forcing a block/continue in that situation produces a wasted
rewrite the user never sees before their own next message lands.

`is_genuine_user`/`text_of` are the CANONICAL implementations — MOVED here
from swe_stop_response_format.py, which now imports them back. Do not
duplicate this logic elsewhere.

Transcript JSONL signals of a mid-turn user message (verified in real
transcripts):
  - a `type: "attachment"` record whose `attachment.type` is
    `"queued_command"` with `humanTurn: true` OR `origin.kind == "human"`;
  - a `type: "queue-operation"` record with `operation: "enqueue"`.

A genuine user prompt that STARTS a turn is a `type: "user"` record whose
content is not tool_result-only and not a system/command wrapper (see
`is_genuine_user`). `user_spoke_mid_turn` looks ONLY at records AFTER the
last such genuine user record — a queued_command attachment that arrived
BEFORE it (i.e. consumed by a prior turn already) must not count.
"""
import json
import os


# ---------------------------------------------------------------------------
# text_of / is_genuine_user — MOVED from swe_stop_response_format.py.
# ---------------------------------------------------------------------------
def text_of(content):
    """Extract plain text from a message content field (str or block list)."""
    if isinstance(content, str):
        return content
    out = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text", ""))
    return "\n".join(out)


def is_genuine_user(rec):
    """True for a real user message (not tool_result plumbing, not meta)."""
    if rec.get("type") != "user":
        return False
    msg = rec.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        # tool_result-only entries are plumbing, not the user speaking
        if all(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return False
    text = text_of(content)
    if not text.strip():
        return False
    # command / hook / system-reminder wrappers are not the user speaking
    if text.lstrip().startswith(("<local-command", "<command-", "<system-reminder", "[SYSTEM NOTIFICATION")):
        return False
    # Stop-hook-generated feedback text is not the user speaking either.
    if text.lstrip().startswith("Stop hook feedback:"):
        return False
    return True


def ends_with_question(text):
    """True when the reply's final non-blank paragraph ends with a question
    mark — such a reply is asking the user something and must not be forced
    into a rewrite/continue by a Stop gate.

    MOVED from swe_stop_response_format.py (was a module-local helper there).
    """
    stripped = (text or "").rstrip()
    if not stripped:
        return False
    # Ignore trailing closing punctuation/quotes/markdown emphasis after '?'.
    tail = stripped.rstrip("`*_\"')]} \n\t")
    return tail.endswith("?")


# ---------------------------------------------------------------------------
# Mid-turn user-message detection
# ---------------------------------------------------------------------------
def queued_command_prompt_text(rec):
    """If `rec` is a human queued_command attachment, return its prompt text
    (joined from `attachment.prompt` text blocks); else None.

    Exposed (not just internal) so callers that need the queued prompt text
    as a turn-boundary marker — e.g. word-count resets in the response-format
    gate's read_transcript — don't re-derive the attachment shape themselves.
    """
    if rec.get("type") != "attachment":
        return None
    attachment = rec.get("attachment") or {}
    if attachment.get("type") != "queued_command":
        return None
    is_human = attachment.get("humanTurn") is True
    if not is_human:
        origin = attachment.get("origin") or {}
        is_human = origin.get("kind") == "human"
    if not is_human:
        return None
    return text_of(attachment.get("prompt"))


def _is_mid_turn_signal(rec):
    """True when `rec` is a queued_command/queue-operation record indicating
    the user typed something while the assistant was still working."""
    rtype = rec.get("type")
    if rtype == "attachment":
        return queued_command_prompt_text(rec) is not None
    if rtype == "queue-operation":
        return rec.get("operation") == "enqueue"
    return False


def user_spoke_mid_turn(transcript_path):
    """True when, after the LAST genuine user prompt record in the
    transcript, there is a queued_command attachment (humanTurn true or
    origin.kind == "human") or a queue-operation enqueue — i.e. the user
    typed a follow-up message before the assistant's current turn ended.

    Missing/unreadable transcript -> False (fail safe: never suppress a
    gate's normal behavior just because the transcript could not be read).
    """
    if not transcript_path:
        return False
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return False

    last_genuine_idx = -1
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            records.append(None)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            records.append(None)
            continue
        records.append(rec)
        if is_genuine_user(rec):
            last_genuine_idx = len(records) - 1

    if last_genuine_idx == -1:
        return False

    for rec in records[last_genuine_idx + 1:]:
        if rec is None:
            continue
        if _is_mid_turn_signal(rec):
            return True
    return False
