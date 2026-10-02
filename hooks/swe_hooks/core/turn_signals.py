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
import re


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
# Unresolved-item detection (final reply → AskUserQuestion gate)
# ---------------------------------------------------------------------------
_FENCED_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_URL_RE = re.compile(r"https?://\S+")
# A short standalone line (markdown heading, bold, or bare label) naming a
# section of open items the user still has to act on.
_PENDING_HEADING_RE = re.compile(
    r"^(?:before (?:fixing|proceeding|continuing|implementing|merging|deploying)"
    r"|open (?:questions?|items?|issues?)|questions?(?: for you)?"
    r"|pending(?: items?| tasks?| decisions?)?|outstanding(?: items?| tasks?)?"
    r"|unresolved(?: items?| questions?)?"
    r"|needs? (?:your )?(?:decision|input|confirmation|answer)s?"
    r"|decisions? (?:needed|required|for you)|remaining(?: work| tasks?| items?)?"
    r"|follow[- ]?ups?|to[- ]?dos?)$",
    re.IGNORECASE,
)
_MAX_HEADING_LEN = 40
# Indirect asks phrased as statements — they still leave a decision with the
# user ("Tell me if you want it removed.", "Happy to add that too.").
_INVITE_RE = re.compile(
    r"\b(?:tell me|let me know|say the word|ping me|confirm)\b.*\b(?:if|whether|which|when|what|how)\b"
    r"|\bif you(?:'d| would)? (?:want|like|prefer|need)\b"
    r"|\b(?:i can|i could|happy to|glad to)\b(?!')(?:.*\b(?:also|too|instead)\b)"
    r"|\b(?:i can|i could)(?!')\s+(?:also\s+|just\s+|then\s+)?(?:make|add|change|fix|implement|remove|switch|stop|update|rename|refactor|write|create|drop|run|re-?run)\b"
    r"|\b(?:want|would you like) me to\b"
    r"|\byour call\b|\bup to you\b",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")
# A real question ends in a word (or closing quote/paren) then '?'; a bare
# '?' after a space is an operator fragment ("the ?? fallback").
_QUESTION_END_RE = re.compile(r"[\w\"')\]]\?$")


def _strip_non_prose(text):
    """Drop code, URLs and blockquote lines — '?' there is not a question."""
    text = _FENCED_CODE_RE.sub("", text)
    text = _INLINE_CODE_RE.sub("", text)
    text = _URL_RE.sub("", text)
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(">"))


def unresolved_items(text):
    """Return the open questions, indirect asks ("Tell me if you want it
    removed.") and pending-item section headings found ANYWHERE in `text`
    (not just its final paragraph), in order. Empty list means the reply
    leaves nothing for the user to resolve."""
    prose = _strip_non_prose(text or "")
    items = []
    for line in prose.splitlines():
        label = line.strip().strip("#*_ ").rstrip(":").strip("*_ ")
        if label and len(label) <= _MAX_HEADING_LEN and _PENDING_HEADING_RE.match(label):
            items.append(f"[section] {label}")
            continue
        for sentence in _SENTENCE_RE.findall(line):
            sentence = sentence.strip().lstrip("-*#0123456789.) ").strip()
            if sentence and (_QUESTION_END_RE.search(sentence) or _INVITE_RE.search(sentence)):
                items.append(sentence)
    return items


def final_reply_text(transcript_path):
    """Assistant text emitted AFTER the last tool call of the current turn —
    the closing reply the user actually reads. Text written before a later
    tool call (e.g. before an AskUserQuestion) is excluded. Missing/unreadable
    transcript -> ""."""
    if not transcript_path:
        return ""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_genuine_user(rec) or queued_command_prompt_text(rec) is not None:
            parts = []
            continue
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        for block in content or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                parts = []
            elif block.get("type") == "text":
                parts.append(block.get("text", ""))
    return "\n".join(parts)


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
