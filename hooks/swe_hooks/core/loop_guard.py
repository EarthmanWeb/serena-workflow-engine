"""Pure loop/oscillation detection over the session event stream.

The FSM graph has intentional cycles (EXECUTE<->CHECKPOINT, VERIFY->EXECUTE,
CLASSIFY->CLARIFY, ARCH_REVIEW self-loop). This module bounds them
mechanically: count how many times a session has crossed a given edge, and
compare it against the caps declared in states.json's "loopCaps".

Every function here is pure (state_events in, answer out) so it can be
tested against synthetic event lists without touching the filesystem. The
StateManager integration (transition_to) is the only caller that reads the
real stream from disk, and it degrades to a no-op when the stream is
unavailable — a missing/unreadable stream must never block a transition.

Event shape (see core/stream.py): a 'state' event is
    {"t": <epoch>, "type": "state", "from_s": <state>, "to_s": <state>, "s": <session_id>}
"""
from typing import Dict, List, Optional, Tuple


def edge_key(a: str, b: str) -> str:
    """Canonical directed edge key 'A->B', as used in transition_to's own
    bookkeeping. loopCaps entries may instead use the bidirectional form
    'A<->B' (see bidirectional_key) to count both directions together."""
    return f"{a}->{b}"


def bidirectional_key(a: str, b: str) -> str:
    """Canonical bidirectional edge key. Sorted so (a, b) and (b, a) produce
    the same key regardless of call order."""
    lo, hi = sorted((a, b))
    return f"{lo}<->{hi}"


def _state_events(state_events: List[dict]) -> List[dict]:
    return [e for e in state_events if isinstance(e, dict) and e.get('type') == 'state']


def count_edge_traversals(state_events: List[dict], a: str, b: str, bidirectional: bool = False) -> int:
    """Count how many times the session crossed edge a->b (or, if
    bidirectional, a->b or b->a) among 'state' events.

    state_events is the full (or task-scoped) event list for a session, as
    returned by stream.events_since_task_start() or a raw read of the
    session's .jsonl stream.
    """
    count = 0
    for e in _state_events(state_events):
        frm, to = e.get('from_s'), e.get('to_s')
        if frm == a and to == b:
            count += 1
        elif bidirectional and frm == b and to == a:
            count += 1
    return count


def _lookup_cap(caps: Dict[str, int], a: str, b: str) -> Tuple[Optional[int], bool]:
    """Find the cap governing edge a->b, checking directed then bidirectional
    key forms. The bidirectional form 'X<->Y' is looked up in BOTH orderings
    ('A<->B' and 'B<->A') since states.json writes it in whichever order
    reads naturally (e.g. "WF_EXECUTE<->WF_CHECKPOINT"), not sorted order.
    Returns (cap_or_None, is_bidirectional).
    """
    directed = edge_key(a, b)
    if directed in caps:
        return caps[directed], False
    for bidi in (f"{a}<->{b}", f"{b}<->{a}"):
        if bidi in caps:
            return caps[bidi], True
    return None, False


def check_loop_cap(state_events: List[dict], a: str, b: str, caps: Dict[str, int]) -> Tuple[bool, int, Optional[int], str]:
    """Check whether taking edge a->b again would stay within its loop cap.

    Args:
        state_events: session's 'state' events (already-taken transitions;
            does NOT include the prospective a->b move being checked).
        a, b: the edge about to be traversed.
        caps: loopCaps dict, e.g. {"WF_EXECUTE<->WF_CHECKPOINT": 20, ...}.

    Returns:
        (ok, count, cap, message)
          ok: True if uncapped, or count+1 (this traversal) would not exceed cap.
          count: prior traversals of this edge found in state_events.
          cap: the cap that applies, or None if this edge is uncapped.
          message: human-readable explanation (empty when ok and uncapped).
    """
    cap, bidirectional = _lookup_cap(caps, a, b)
    count = count_edge_traversals(state_events, a, b, bidirectional=bidirectional)

    if cap is None:
        return True, count, None, ""

    prospective = count + 1
    if prospective > cap:
        arrow = "<->" if bidirectional else "->"
        return False, count, cap, (
            f"Loop cap exceeded: {a}{arrow}{b} has been traversed {count} time(s) this session "
            f"(cap {cap}). Use `/swe-goto {b} --force` to override, or ask the user how to proceed "
            f"instead of continuing to cycle."
        )
    return True, count, cap, ""


def detect_oscillation(state_events: List[dict], window: int = 6) -> Optional[str]:
    """Detect an A->B->A->B... oscillation in the most recent `window` state
    events. Returns a warning string if found, else None.

    This does not block anything — transition_to allows the move but appends
    the warning to its returned message, since a genuine oscillation usually
    means the agent is stuck rather than making progress even when under cap.
    """
    events = _state_events(state_events)
    if len(events) < 4:
        return None
    recent = events[-window:] if window > 0 else events
    # Build the sequence of states visited: from_s of first event, then to_s
    # of every event in order.
    if not recent:
        return None
    seq = [recent[0].get('from_s')] + [e.get('to_s') for e in recent]
    # Look for an alternating A,B,A,B pattern of length >= 4 at the tail.
    n = len(seq)
    if n < 4:
        return None
    a, b = seq[-2], seq[-1]
    if a is None or b is None or a == b:
        return None
    i = n - 1
    run = 1
    while i >= 2 and seq[i - 2] == seq[i] and seq[i - 1] != seq[i]:
        run += 1
        i -= 2
    # run counts how many A/B pairs alternate at the tail; >=2 full round
    # trips (A->B->A->B) means at least 4 states in the alternating tail.
    if run >= 2:
        return f"Oscillation detected: {a} <-> {b} repeating ({run} round trips in the last {len(recent)} transitions)."
    return None
