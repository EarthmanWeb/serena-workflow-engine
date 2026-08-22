#!/usr/bin/env python3
"""Stop-hook gate: enforce a terse response format.

Blocks the stop (once) when the assistant's prose since the last genuine user
message exceeds the word budget and the user did not ask for detail, OR when the
reply emits recap/summary/self-congratulation scaffolding. The block reason
instructs a terse restatement.

Generic, non-project-specific: budget + enabled state come from the project's
swe-setup-complete.json "response_format" block (see core.config
get_response_format_config). ON by default; a project opts out with
{"response_format": {"enabled": false}}. Skips silently when SWE is bypassed or
the project is uninitialized.

Runtime state lives under .serena/streams/:
  - response-format-offenders.log  — one entry per blocked turn (regex tuning)
  - .format-gate-block-<session>   — sentinel read by the UserPromptSubmit
    reminder hook (swe_prompt_format_reminder.py), which surfaces the budget on
    the next turn and clears it.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.config import (
        get_project_root,
        get_response_format_config,
        resolve_setup_state,
    )
    from swe_hooks.core.stream import get_stream_dir
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "Stop")


# Detail is opt-in via an EXPLICIT literal token only: the message must start
# with `DETAIL:` (or `DETAIL -`) to license a long reply. Natural-language
# phrasing ("why", "explain", "be thorough") stays under the terse floor.
DETAIL_TRIGGERS = re.compile(r"^\s*DETAIL\s*[:\-]", re.IGNORECASE)

# Recap / summary scaffolding that must never be emitted. These fire regardless
# of word count — they are format violations, not length.
BANNED_PATTERNS = [
    (re.compile(r"^\s*#{1,4}\s*(summary|recap|status|what (i|we) (did|changed)|"
                r"final (state|status)|outstanding|next steps|remaining work)\b",
                re.IGNORECASE | re.MULTILINE), "recap/summary heading"),
    (re.compile(r"^\s*\*{2}(summary|recap|status|done( and verified)?|completed|"
                r"outstanding|still (to do|blocked|open)|not started|next steps?)\b",
                re.IGNORECASE | re.MULTILINE), "recap/summary bold-label block"),
    (re.compile(r"\b(to (summari[sz]e|recap)|in summary|in short|to sum up|"
                r"here'?s (a |the )?(summary|recap|rundown|breakdown) of what)\b",
                re.IGNORECASE), "summary phrase"),
    (re.compile(r"^\s*(two|three|four|\d+) (decisions?|things?|items?|questions?) "
                r"(for you|remain|left|outstanding)\b", re.IGNORECASE | re.MULTILINE),
     "enumerated hand-back preamble"),
    # Announcing what you are about to do instead of doing it.
    (re.compile(r"^\s*(let me|i'?ll|i am going to|i'?m going to|next,? i)\b",
                re.IGNORECASE | re.MULTILINE), "narrating the next action"),
    # Meta-commentary about one's own output or process.
    (re.compile(r"\b(as (i|you) (noted|mentioned|said) (above|earlier)|"
                r"worth (noting|flagging)\b|"
                r"(one|two|a few) things? (you should know|worth knowing)|"
                r"before i (move on|continue|proceed)\b)",
                re.IGNORECASE), "meta-commentary preamble"),
    # Self-scoring / verification theatre in place of the result.
    (re.compile(r"^\s*\*{0,2}(all|everything) (\d+ )?(items?|tasks?|tests?) "
                r"(are )?(green|passing|complete|done)\b",
                re.IGNORECASE | re.MULTILINE), "self-congratulatory status line"),
    # Unsolicited closing offer to keep going — the trailing "want me to…?" tail.
    (re.compile(r"\b(want me to|would you like me to|shall i|should i|"
                r"do you want me to|let me know if you(?:'d| would| want)|"
                r"happy to|i can also|if you(?:'d| would) like,? i)\b",
                re.IGNORECASE), "unsolicited closing offer"),
]


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested directly)
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
    return True


def prose_words(text):
    """Count words outside fenced code blocks; tables/bullets count at half weight."""
    no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    full, half = 0, 0
    for line in no_code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        n = len(stripped.split())
        if stripped.startswith(("|", "- ", "* ", "> ")) or re.match(r"^\d+\.\s", stripped):
            half += n
        else:
            full += n
    return full + half // 2


_WORD_RE = re.compile(r"[a-z0-9]+")
DUP_SIMILARITY_THRESHOLD = 0.6
DUP_MIN_WORDS = 15


def word_bag(text):
    """Set of lowercased word tokens outside fenced code blocks."""
    no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return set(_WORD_RE.findall(no_code.lower()))


def similarity(a, b):
    """Jaccard similarity of two word bags; 0.0 when either is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def duplicate_answer(assistant_since_user):
    """True when two substantial messages this turn are near-duplicates.

    A message under DUP_MIN_WORDS prose words (short acks) is ignored, so a
    "Done." plus one real answer never trips the check.
    """
    bags = []
    for text in assistant_since_user:
        bags.append(word_bag(text) if prose_words(text) >= DUP_MIN_WORDS else None)
    for i in range(len(bags)):
        for j in range(i + 1, len(bags)):
            if bags[i] is None or bags[j] is None:
                continue
            if similarity(bags[i], bags[j]) >= DUP_SIMILARITY_THRESHOLD:
                return True
    return False


def evaluate(assistant_since_user, last_user_text, terse_limit, detail_limit, retry):
    """Decide whether to block. Pure function — no IO.

    Args:
        assistant_since_user: list of assistant text messages since the last
            genuine user message (chronological).
        last_user_text: the last genuine user message text.
        terse_limit / detail_limit: word budgets.
        retry: True when this is a stop_hook_active retry (judge only newest msg).

    Returns:
        (reason, scanned_text, word_count) when the turn should block, else
        (None, scanned_text, word_count).
    """
    reply = "\n".join(assistant_since_user)
    detail_requested = bool(DETAIL_TRIGGERS.search(last_user_text or ""))
    limit = detail_limit if detail_requested else terse_limit

    words = prose_words(reply)
    worst_single = max((prose_words(t) for t in assistant_since_user), default=0)

    # On a retry, judge ONLY the newest message — the pre-block text is still in
    # `reply` and would re-trigger forever.
    scanned = assistant_since_user[-1] if (retry and assistant_since_user) else reply
    violations = [label for pat, label in BANNED_PATTERNS if pat.search(scanned)]

    if retry and not violations:
        return None, scanned, words

    if violations:
        reason = (
            f"RESPONSE FORMAT GATE: emitted {', '.join(violations)} — NO recap, NO "
            "status summary, NO closing wrap-up. The work is already visible in the "
            "tool calls. Re-answer with ONLY the result or the single question you "
            "need answered (<=10 lines). Do not apologize."
        )
        return reason, scanned, words

    # A repeated answer blocks even when each copy is individually under budget.
    # Skip on retry: retry judges only the newest message, and the earlier
    # pre-block text lingers in `reply` by design.
    if not retry and duplicate_answer(assistant_since_user):
        reason = (
            "RESPONSE FORMAT GATE: emitted a repeated answer — keep ONLY the last "
            "(tightest) version; the earlier restatement should not have shipped. "
            "Re-answer with a single terse version (<=10 lines). Do not apologize."
        )
        return reason, scanned, words

    if words > limit or worst_single > limit:
        which = (
            f"{words} prose words this turn" if words > limit
            else f"a single message of {worst_single} prose words"
        )
        reason = (
            f"RESPONSE FORMAT GATE: {which} "
            f"(budget {limit}; detail {'requested' if detail_requested else 'NOT requested'}). "
            "Lead with the answer/action, bullets over paragraphs, no preamble/recap/"
            "closing summary. Output ONLY a terse restatement of the essential result "
            "(<=10 lines). Do not apologize or explain the length."
        )
        return reason, scanned, words

    return None, scanned, words


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def sentinel_path(session):
    """Per-session flag file read by swe_prompt_format_reminder.py."""
    return os.path.join(get_stream_dir(), f".format-gate-block-{session}")


def mark_blocked(session):
    try:
        with open(sentinel_path(session), "w") as f:
            f.write("blocked")
    except OSError:
        pass


def offender_log_path():
    return os.path.join(get_stream_dir(), "response-format-offenders.log")


def log_offender(session, reason, user_text, reply, word_count):
    """Append one blocked turn (prompt + offending reply) for later regex tuning."""
    try:
        with open(offender_log_path(), "a", encoding="utf-8") as f:
            f.write(
                f"\n{'=' * 72}\n"
                f"session={session} words={word_count}\n"
                f"reason: {reason}\n"
                f"--- user ---\n{(user_text or '').strip()[:500]}\n"
                f"--- reply ({len(reply.split())} words) ---\n{reply.strip()}\n"
            )
    except OSError:
        pass


def read_transcript(transcript_path):
    """Return (last_user_text, [assistant texts since last genuine user])."""
    last_user_text = ""
    assistant_since_user = []
    with open(transcript_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if is_genuine_user(rec):
                last_user_text = text_of((rec.get("message") or {}).get("content"))
                assistant_since_user = []
            elif rec.get("type") == "assistant":
                t = text_of((rec.get("message") or {}).get("content"))
                if t.strip():
                    assistant_since_user.append(t)
    return last_user_text, assistant_since_user


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    transcript_path = data.get("transcript_path")
    if not transcript_path:
        sys.exit(0)

    project_root = get_project_root()

    # Skip when SWE is bypassed or the project was never initialized — the gate
    # is opinionated and must not fire on projects that never opted into SWE.
    setup = resolve_setup_state(project_root)
    if setup.get("bypassed") or not setup.get("initialized"):
        sys.exit(0)

    cfg = get_response_format_config()
    if not cfg.get("enabled"):
        sys.exit(0)

    retry = bool(data.get("stop_hook_active"))
    session = os.path.splitext(os.path.basename(transcript_path or "unknown"))[0]

    try:
        last_user_text, assistant_since_user = read_transcript(transcript_path)
    except OSError:
        sys.exit(0)

    reason, scanned, words = evaluate(
        assistant_since_user, last_user_text,
        cfg["terse_limit"], cfg["detail_limit"], retry,
    )

    if reason:
        mark_blocked(session)
        log_offender(session, reason.split(" — ")[0], last_user_text, scanned, words)
        print(json.dumps({"decision": "block", "reason": reason}))

    sys.exit(0)


if __name__ == "__main__":
    main()
