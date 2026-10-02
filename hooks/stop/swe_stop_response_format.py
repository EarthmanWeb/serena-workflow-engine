#!/usr/bin/env python3
"""Stop-hook gate: enforce a terse response format.

Blocks the stop (at most ONCE per user turn) when the assistant's prose since
the last genuine user message exceeds the word budget and the user did not ask
for detail, OR when the reply emits recap/summary/self-congratulation
scaffolding. The block reason instructs a terse restatement. A second overage
in the SAME user turn emits a WARN attachment (additionalContext, never a
second block) — every avoided block saves a full regenerated close.

Detail budget: licensed by the literal `DETAIL:` prefix OR by natural-language
detail asks in the last user message — review / report / explain / analysis /
"summary of" / total / "walk me through" / why, word-boundary matched,
case-insensitive (see detail_requested). This deliberately REPLACES the old
"literal DETAIL: prefix ONLY" contract, which blocked the turn answering
"provide me with a total review of token usage".

Never blocks:
  - when the session's workflow state is WF_DONE (final deliverable turn);
  - on a stop_hook_active retry (main() exits before evaluating);
  - for the DIAGNOSIS VERIFICATION: block, which is stripped before any
    counting and counts as zero words (see strip_diagnosis_verification).

Generic, non-project-specific: budget + enabled state come from the project's
swe-setup-complete.json "response_format" block (see core.config
get_response_format_config). ON by default; a project opts out with
{"response_format": {"enabled": false}}. Skips silently when SWE is bypassed or
the project is uninitialized.

Runtime state lives under .serena/streams/:
  - response-format-offenders.log  — one entry per blocked turn (regex tuning)
  - .format-gate-block-<session>   — sentinel JSON {"fp", "count"}: fp is a
    stable fingerprint of the last genuine user message (identifies the user
    turn for the one-block-per-turn rule), count the overages seen this turn.
    Read back by this gate, and (existence only) by the UserPromptSubmit
    reminder hook (swe_prompt_format_reminder.py), which surfaces the budget
    on the next turn and clears it.
"""
import hashlib
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
    from swe_hooks.core.output import output_status
    from swe_hooks.core.state_manager import StateManager
    from swe_hooks.core.stream import get_stream_dir
    from swe_hooks.core.turn_signals import (
        ends_with_question,
        is_genuine_user,
        queued_command_prompt_text,
        text_of,
        user_spoke_mid_turn,
    )
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "Stop")


# Detail is opt-in two ways:
#   1. the literal `DETAIL:` (or `DETAIL -`) prefix — the original token;
#   2. natural-language detail asks — word-boundary, case-insensitive matches
#      on: review, report, explain, analysis, "summary of", total,
#      "walk me through", why.
# The old contract (literal prefix ONLY) is deliberately gone: it blocked the
# turn answering "provide me with a total review of token usage".
DETAIL_TRIGGERS = re.compile(r"^\s*DETAIL\s*[:\-]", re.IGNORECASE)
NATURAL_DETAIL_TRIGGERS = re.compile(
    r"\b(?:review|report|explain|analysis|summary of|total|walk me through|why)\b",
    re.IGNORECASE,
)


def detail_requested(last_user_text):
    """True when the last genuine user message licenses the detail budget:
    a literal DETAIL: prefix, or a natural-language detail trigger."""
    text = last_user_text or ""
    return bool(DETAIL_TRIGGERS.search(text) or NATURAL_DETAIL_TRIGGERS.search(text))

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
# text_of / is_genuine_user MOVED to swe_hooks.core.turn_signals (imported
# above) — re-exported here (module attribute) so existing callers/tests
# using `gate.text_of` / `gate.is_genuine_user` keep working unchanged.

# A line that is essentially a file reference / path listing — an absolute
# or relative filesystem path, optionally with a leading bullet/number marker
# and a trailing note. Such lines are the mechanical "here are the files"
# output the budget must not penalize; they carry no prose content to judge.
_FILE_REF_LINE_RE = re.compile(
    r"^(?:[-*]\s+|\d+\.\s+)?`?(?:/|\.\./|\./|~/)?(?:[\w.-]+/)+[\w.-]+\.\w+`?"
    r"(?:\s*[:\-—]\s*.*)?$"
)


def prose_words(text):
    """Count words outside fenced code blocks, tables, and file-reference/
    list-of-paths lines; bullets/tables/numbered lines count at half weight."""
    no_code = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    full, half = 0, 0
    for line in no_code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _FILE_REF_LINE_RE.match(stripped):
            continue
        n = len(stripped.split())
        if stripped.startswith(("|", "- ", "* ", "> ")) or re.match(r"^\d+\.\s", stripped):
            half += n
        else:
            full += n
    return full + half // 2


# ends_with_question MOVED to swe_hooks.core.turn_signals (imported above);
# re-exported as a module attribute for existing callers/tests (gate.ends_with_question).

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


# G4: the diagnosis verification block is EXEMPT from the word budget and must
# never trigger a block. Exact shape stripped (counts as zero words):
#   DIAGNOSIS VERIFICATION:
#   - MECHANISM: <exact before/after code path producing the symptom>
#   - TIMING: <the change postdates last-known-good — explains WHY NOW>
#   - COUNTERFACTUAL: <prior state demonstrably produced the working behavior>
# plus any line containing "candidate — unverified" (the unmet-check label).
_DIAG_HEADER_PREFIX = "DIAGNOSIS VERIFICATION:"
_DIAG_ITEM_PREFIXES = ("- MECHANISM:", "- TIMING:", "- COUNTERFACTUAL:")
_DIAG_UNVERIFIED_MARK = "candidate — unverified"


def strip_diagnosis_verification(text):
    """Drop every diagnosis-verification block from `text`. Pure function.

    A block runs from a line starting with "DIAGNOSIS VERIFICATION:" through
    the last CONSECUTIVE line starting with "- MECHANISM:", "- TIMING:", or
    "- COUNTERFACTUAL:". Any line containing "candidate — unverified" is
    dropped wherever it appears. Everything else is kept verbatim.
    """
    out = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if _DIAG_UNVERIFIED_MARK in line:
            i += 1
            continue
        if line.lstrip().startswith(_DIAG_HEADER_PREFIX):
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(_DIAG_ITEM_PREFIXES):
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


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
    # G4: the diagnosis verification block counts as zero words and must never
    # trigger a block — strip it from every message before ANY judging.
    msgs = [strip_diagnosis_verification(t) for t in assistant_since_user]
    reply = "\n".join(msgs)
    wants_detail = detail_requested(last_user_text)
    limit = detail_limit if wants_detail else terse_limit

    words = prose_words(reply)
    worst_single = max((prose_words(t) for t in msgs), default=0)

    # On a retry, judge ONLY the newest message — the pre-block text is still in
    # `reply` and would re-trigger forever.
    scanned = msgs[-1] if (retry and msgs) else reply
    violations = [label for pat, label in BANNED_PATTERNS if pat.search(scanned)]

    if retry and not violations:
        return None, scanned, words

    if violations:
        reason = (
            f"RESPONSE FORMAT GATE: emitted {', '.join(violations)} — NO recap, NO "
            "status summary, NO closing wrap-up. The work is already visible in the "
            "tool calls. Re-answer with ONLY the result; any decision you need from "
            "the user goes through the AskUserQuestion tool, never prose (<=10 lines). "
            "Do not apologize."
        )
        return reason, scanned, words

    # A repeated answer blocks even when each copy is individually under budget.
    # Skip on retry: retry judges only the newest message, and the earlier
    # pre-block text lingers in `reply` by design.
    if not retry and duplicate_answer(msgs):
        reason = (
            "RESPONSE FORMAT GATE: emitted a repeated answer — keep ONLY the last "
            "(tightest) version; the earlier restatement should not have shipped. "
            "Re-answer with a single terse version (<=10 lines). Do not apologize."
        )
        return reason, scanned, words

    # A reply that ends by asking the user a question is not judged against
    # the length budget — it needs an answer before anything else can happen,
    # and forcing a rewrite here would just re-ask the same question tersely.
    if (words > limit or worst_single > limit) and not ends_with_question(reply):
        which = (
            f"{words} prose words this turn" if words > limit
            else f"a single message of {worst_single} prose words"
        )
        reason = (
            f"RESPONSE FORMAT GATE: {which} "
            f"(budget {limit}; detail {'requested' if wants_detail else 'NOT requested'}). "
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
    """Per-session flag file: JSON {"fp", "count"} identifying the user turn
    of the last block. Read back by this gate (one-block-per-turn) and, by
    existence only, by swe_prompt_format_reminder.py."""
    return os.path.join(get_stream_dir(), f".format-gate-block-{session}")


def turn_fingerprint(user_text):
    """Stable fingerprint of the last genuine user message — identifies one
    user turn across the Stop events it produces (one-block-per-turn)."""
    return hashlib.sha1((user_text or "").strip().encode("utf-8")).hexdigest()


def read_block_record(session):
    """Return the sentinel's {"fp": str, "count": int}, or None when absent
    or legacy/unparseable (pre-F2 sentinels held the bare word 'blocked')."""
    try:
        with open(sentinel_path(session), encoding="utf-8") as f:
            rec = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict) or "fp" not in rec:
        return None
    return rec


def mark_blocked(session, fp, count):
    try:
        with open(sentinel_path(session), "w", encoding="utf-8") as f:
            json.dump({"fp": fp, "count": count}, f)
    except OSError:
        pass


TURN_WARN_TEXT = (
    "RESPONSE FORMAT WARN: over budget again in the same user turn — the gate "
    "blocks at most once per turn, so this stop is allowed. Keep it terse "
    "anyway: lead with the result, <=10 lines, no recap."
)


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
    """Return (last_user_text, [assistant texts since last genuine user]).

    A queued_command human attachment is ALSO treated as a turn boundary:
    it means the user typed a follow-up mid-turn, so prose the assistant
    wrote BEFORE that message must not be counted toward the CURRENT turn's
    word budget — only what the assistant says after the user's new message
    is "this turn"'s reply.
    """
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
                continue
            queued_text = queued_command_prompt_text(rec)
            if queued_text is not None:
                last_user_text = queued_text
                assistant_since_user = []
                continue
            if rec.get("type") == "assistant":
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

    # NEVER block on a stop_hook_active retry — this IS the retry the gate's
    # own prior block produced. Blocking again risks ping-ponging with
    # swe_stop_continue_working (capped at 3) instead of letting the turn end.
    # At most one forced rewrite happens per turn; the retry always passes.
    if retry:
        sys.exit(0)

    session = os.path.splitext(os.path.basename(transcript_path or "unknown"))[0]

    # NEVER block the final deliverable turn: WF_DONE exits silently.
    if StateManager(project_root, session_id=session).get_current_state() == "WF_DONE":
        sys.exit(0)

    # The user already typed a follow-up before this Stop event — forcing a
    # block/rewrite here produces a wasted turn the user will not even see
    # before their own next message lands. Skip silently.
    if user_spoke_mid_turn(transcript_path):
        sys.exit(0)

    try:
        last_user_text, assistant_since_user = read_transcript(transcript_path)
    except OSError:
        sys.exit(0)

    reason, scanned, words = evaluate(
        assistant_since_user, last_user_text,
        cfg["terse_limit"], cfg["detail_limit"], retry,
    )

    if reason:
        mode = cfg.get("mode", "advise")
        fp = turn_fingerprint(last_user_text)

        if mode == "advise":
            # NEVER emit decision:block in advise mode — still record the
            # overage (mark_blocked) so swe_prompt_format_reminder.py
            # surfaces the budget on the NEXT prompt, and log it for tuning.
            # No stdout beyond the empty-allow default: exit silently.
            mark_blocked(session, fp, 1)
            log_offender(session, reason.split(" — ")[0], last_user_text, scanned, words)
            sys.exit(0)

        prior = read_block_record(session)
        if prior and prior.get("fp") == fp:
            # This user turn already consumed its one block — WARN attachment
            # only (plain additionalContext, no decision:block).
            mark_blocked(session, fp, int(prior.get("count", 1)) + 1)
            output_status(TURN_WARN_TEXT, event="Stop")
        mark_blocked(session, fp, 1)
        log_offender(session, reason.split(" — ")[0], last_user_text, scanned, words)
        print(json.dumps({"decision": "block", "reason": reason}))

    sys.exit(0)


if __name__ == "__main__":
    main()
