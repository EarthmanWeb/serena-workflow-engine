"""State machine manager for workflow transitions.

State is stored in WM files (session-isolated), NOT in a global state file.
This allows multiple concurrent sessions without state conflicts.
"""

import json
import os
from typing import Dict, Any, Optional, Tuple, List
from .config import (
    load_workflow_state, save_workflow_state,
    get_most_recent_working_memory, get_working_memory_filename,
    read_working_memory_state, write_working_memory_state,
    read_state_file, write_state_file,
    get_project_root
)
from .session import (
    extract_session_id, find_working_memory_for_session,
    validate_working_memory_session
)


# Cache for transition matrix (kept for backward compatibility — tests and
# other modules poke this attribute directly via reset_caches()).
_transition_matrix_cache = None

# Cache for the full states.json document, invalidated by file mtime so a
# states.json edit (or a test writing a temp copy) is picked up without
# requiring an explicit reset_caches() call. Tuple of (mtime, data) or None.
_states_doc_cache = None


def get_states_file_path() -> str:
    """Path to state-machine/states.json, derived from this file's location."""
    # Derive plugin root from __file__: core/ -> swe_hooks/ -> hooks/ -> plugin root
    plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(plugin_root, 'state-machine', 'states.json')


def load_states_document() -> Dict[str, Any]:
    """Load the full states.json document, cached and invalidated by mtime.

    This is the single source of truth for the transition matrix, per-state
    ranks, subflow names, loop caps, and the readAdvance flag. Returns {} if
    the file is missing or invalid (callers fail closed on that).
    """
    global _states_doc_cache

    states_file = get_states_file_path()
    try:
        mtime = os.path.getmtime(states_file)
    except OSError:
        return {}

    if _states_doc_cache is not None and _states_doc_cache[0] == mtime:
        return _states_doc_cache[1]

    try:
        with open(states_file, 'r') as f:
            data = json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}

    _states_doc_cache = (mtime, data)
    return data


def load_transition_matrix() -> Dict[str, List[str]]:
    """Load the transition matrix from states.json.

    Returns:
        Dict mapping state names to list of valid next states.
    """
    global _transition_matrix_cache

    if _transition_matrix_cache is not None:
        return _transition_matrix_cache

    data = load_states_document()
    _transition_matrix_cache = data.get('transitionMatrix', {})
    return _transition_matrix_cache


def load_subflows() -> List[str]:
    """Documented non-FSM procedures (WF_INIT, WF_CLEANUP, ...).

    These have memories/wf/WF_X.md docs but are NOT states.json nodes — they
    are linear procedures, not places the FSM can be "in". set_state must
    never target one.
    """
    data = load_states_document()
    return list(data.get('subflows', []))


def load_loop_caps() -> Dict[str, int]:
    """Loop-traversal caps keyed 'A->B' (directed) or 'A<->B' (either
    direction counted together). See loop_guard.check_loop_cap."""
    data = load_states_document()
    caps = data.get('loopCaps', {})
    return {k: v for k, v in caps.items() if k != 'description' and isinstance(v, int)}


def is_read_advance_enabled() -> bool:
    data = load_states_document()
    return bool(data.get('readAdvance', {}).get('enabled', True))


def is_valid_transition(from_state: str, to_state: str) -> Tuple[bool, str]:
    """Check if a state transition is valid.

    Args:
        from_state: Current state
        to_state: Target state

    Returns:
        Tuple of (is_valid, error_message)
    """
    matrix = load_transition_matrix()

    # FAIL CLOSED: If matrix can't load, only allow init transitions
    if not matrix:
        if from_state in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
            return True, ""
        return False, "BLOCKED: State machine unavailable. Only WF_INIT transitions allowed."

    # Special case: WF_INIT can go anywhere (session start)
    if from_state in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
        return True, ""

    # Special case: WF_CLARIFY can return to caller. This pure, stateless
    # check has no access to "which state entered CLARIFY", so it stays
    # permissive here; StateManager.transition_to enforces the tighter
    # clarify_allowed_targets() rule (previous_state or WF_CLASSIFY /
    # WF_ARCH_REVIEW) where the actual previous_state is known.
    if from_state == "WF_CLARIFY":
        return True, ""

    # Subflows (WF_INIT, WF_CLEANUP, ...) are documented procedures, not FSM
    # states — they never appear as a matrix key. Give a distinct reason so
    # callers (set_state) know not to retry with --force expecting a node.
    if to_state in load_subflows():
        return False, (
            f"BLOCKED: {to_state} is a subflow, not an FSM state — do not set_state to it. "
            f"It is a documented procedure, entered by reading its memory, not by transitioning."
        )

    # Check if from_state exists in matrix
    if from_state not in matrix:
        return False, f"BLOCKED: Unknown state {from_state}. Valid states: {', '.join(matrix.keys())}"

    valid_targets = [t for t in matrix[from_state] if t is not None]

    # Terminal state with no valid transitions
    if not valid_targets:
        return True, ""

    # Check if to_state is valid
    if to_state in valid_targets:
        return True, ""

    # Invalid transition
    return False, (
        f"BLOCKED: Invalid transition {from_state} → {to_state}. "
        f"Valid next states from {from_state}: {', '.join(valid_targets)}"
    )


# Happy-path progression rank. A WF_* read advances state only when it moves
# FORWARD (to an equal-or-higher rank) — so reading the next step navigates,
# but reading-ahead/backward to INSPECT a memory does not jump the FSM. This is
# the targeted fix for the old "accidentally moved to the wrong transition" bug
# while restoring the natural read-your-way-forward flow.
#
# Ranks live ONLY in states.json (per-state "rank" field) — there is no
# hardcoded fallback table. If states.json is missing/unreadable, or has no
# states with a "rank" field, ranks are simply unavailable: read-advance is
# then disabled outright (see is_forward_read_transition) rather than silently
# guessing at an ordering from a stale hardcoded copy. Subflow names (WF_INIT,
# WF_CLEANUP, ...) are documented procedures, not states.json nodes, and
# never carry a rank — they never advance via a read, by design.
def load_forward_rank() -> Dict[str, int]:
    """Load per-state ranks from states.json's "rank" fields.

    Single source of truth for progression order. Returns {} if states.json
    is missing/invalid or no state declares a "rank" — callers must treat an
    empty result as "ranks unavailable", not as "everything is rank 0".
    """
    data = load_states_document()
    states = data.get('states', {})
    ranks = {name: info.get('rank') for name, info in states.items() if isinstance(info, dict) and 'rank' in info}
    return ranks


# Populated at import time; refreshed on demand by callers that want the
# latest ranks (is_forward_read_transition() always calls load_forward_rank()
# fresh so an states.json edit takes effect without restarting the process —
# the mtime cache in load_states_document() keeps this cheap). Empty dict
# when ranks are unavailable — kept as a module attribute for tests/back-compat.
_FORWARD_RANK = load_forward_rank()


def clarify_allowed_targets(previous_state: Optional[str]) -> List[str]:
    """Valid return targets from WF_CLARIFY.

    WF_CLARIFY is a gate, not a wildcard: it may only return to the state it
    was entered from (if known), or fall back to WF_CLASSIFY / WF_ARCH_REVIEW
    — the two states that route into clarification in the first place.
    """
    targets = ["WF_CLASSIFY", "WF_ARCH_REVIEW"]
    if previous_state and previous_state not in targets and previous_state != "WF_CLARIFY":
        targets = [previous_state] + targets
    return targets


def is_forward_read_transition(from_state: str, to_state: str) -> Tuple[bool, str]:
    """Decide whether READING to_state's memory should advance the FSM.

    A read advances state only when BOTH hold:
      1. from_state → to_state is a valid matrix transition, AND
      2. it is a FORWARD move (to_state rank >= from_state rank) and to_state
         is not a return-only gate (WF_CLARIFY).

    Reading a non-adjacent, backward, or gate memory (i.e. inspecting it, or
    reading ahead during analysis) returns False — the read is logged as
    "ON STEP" but the FSM is NOT moved. This restores the pre-v4 read-driven
    flow without the accidental wrong-direction jumps.

    Returns (should_transition, reason).
    """
    # Init bootstrap (WF_INIT → WF_CLASSIFY) is handled explicitly elsewhere.
    if from_state in ("WF_INIT", "UNINITIALIZED", "SessionStart"):
        return False, "init bootstrap handled separately"

    # Never auto-advance INTO the clarify gate via a read.
    if to_state == "WF_CLARIFY":
        return False, "WF_CLARIFY is entered deliberately, not by reading"

    valid, msg = is_valid_transition(from_state, to_state)
    if not valid:
        return False, msg

    # Ranks missing/unreadable (states.json absent, invalid, or declares no
    # ranks): read-advance is DISABLED rather than silently falling back to a
    # hardcoded guess. Fresh lookup (not the module-level _FORWARD_RANK
    # snapshot) so an states.json fix takes effect without a restart.
    ranks = load_forward_rank()
    if not ranks:
        return False, (
            "read-advance disabled: states.json has no per-state ranks "
            "(missing, unreadable, or no state declares \"rank\")"
        )
    if from_state not in ranks or to_state not in ranks:
        return False, (
            f"read-advance disabled: no rank for "
            f"{from_state if from_state not in ranks else to_state} in states.json"
        )

    from_rank = ranks[from_state]
    to_rank = ranks[to_state]
    if to_rank < from_rank:
        return False, (
            f"read-ahead/back: {to_state} (rank {to_rank}) is behind "
            f"{from_state} (rank {from_rank}); inspecting, not navigating"
        )
    return True, f"forward read transition {from_state} → {to_state}"


# State icons for display (15 states - v3.0)
STATE_ICONS = {
    "WF_INIT": "🎬",
    "WF_ONBOARD": "📚",
    "WF_CLASSIFY": "🏷️",
    "WF_RESEARCH": "🔍",
    "WF_CLARIFY": "❓",
    "WF_ARCH_REVIEW": "🔬",
    "WF_EXECUTE": "⚡",
    "WF_CHECKPOINT": "💾",
    "WF_VERIFY": "✅",
    "WF_DEBUG_TDD": "🐛",
    "WF_CONTINUE": "➡️",
    "WF_DONE": "🎉",
    "WF_INITIAL_SETUP": "⚙️",
}

# States that require plan mode
PLAN_MODE_STATES = {
    "WF_ARCH_REVIEW",
}

# States that exit plan mode
EXIT_PLAN_MODE_STATES = {
    "WF_EXECUTE",
    "WF_CHECKPOINT",
    "WF_VERIFY",
    "WF_DEBUG_TDD",
}


def clear_sweep_sentinel(session_id: str) -> None:
    """Remove the per-task Feature Knowledge Sweep sentinel.

    Called on every transition INTO WF_CLASSIFY: each task (including
    same-session follow-ups) must re-verify its sweep before the edit gate
    unlocks. Best-effort — never raises.
    """
    if not session_id:
        return
    try:
        from .stream import get_feature_sentinel_path
        sentinel = get_feature_sentinel_path(session_id, 'sweep')
        if os.path.exists(sentinel):
            os.remove(sentinel)
    except Exception:
        pass


class StateManager:
    """Manages workflow state transitions.

    State is stored in WM files, allowing multiple concurrent sessions.
    Each session has its own WM file with embedded workflow context.
    """

    def __init__(self, cwd: str, wm_filename: str = None, session_id: str = None):
        """Initialize state manager.

        Args:
            cwd: Working directory
            wm_filename: Optional specific WM filename (without .md)
                        If None, finds working memory for session_id
            session_id: Optional session ID for session isolation.
                       If provided, only uses working memory matching this session.
        """
        self.cwd = cwd
        self.wm_filename = wm_filename
        self.wm_filepath = None
        self.session_id = session_id

        # Try to load state from WM with session isolation
        state_data = None
        filepath = None

        if wm_filename:
            # Specific filename provided - use it
            state_data, filepath = read_working_memory_state(cwd, wm_filename, session_id=session_id)
        elif session_id:
            # Session ID provided - find working memory for this session only
            filepath = find_working_memory_for_session(cwd, session_id)
            if filepath:
                state_data, filepath = read_working_memory_state(cwd, filepath.replace('.md', '').split('/')[-1], session_id=session_id)
            else:
                # No WM found — fallback to decoupled state file
                sf = read_state_file(session_id)
                if sf:
                    state_data = {
                        'current_state': sf['current_state'],
                        'session_id': session_id,
                        'clarify_entered_from': sf.get('clarify_entered_from'),
                    }
        else:
            # No session context - fall back to most recent (legacy behavior)
            state_data, filepath = read_working_memory_state(cwd)

        # Validate session ownership if session_id provided
        if filepath and session_id and not validate_working_memory_session(filepath, session_id):
            # Working memory doesn't belong to this session - don't use it
            state_data = None
            filepath = None

        if state_data:
            self.wm_filepath = filepath
            self.wm_filename = filepath.replace('.md', '').split('/')[-1] if filepath else None
            self.state = {
                "current_state": state_data.get("current_state", "WF_INIT"),
                "previous_state": None,
                "session_id": state_data.get("session_id") or session_id,
                "working_memory_file": self.wm_filename,
                "feature_keys": state_data.get("feature_keys", []),
                "edits_since_checkpoint": 0,
                "plan_mode": state_data.get("current_state") in PLAN_MODE_STATES,
                "clarify_entered_from": state_data.get("clarify_entered_from"),
            }
        else:
            self.state = {
                "current_state": "WF_INIT",
                "previous_state": None,
                "session_id": session_id,
                "working_memory_file": None,
                "edits_since_checkpoint": 0,
                "plan_mode": False,
                "clarify_entered_from": None,
            }

    def get_current_state(self) -> str:
        """Get current workflow state."""
        return self.state.get("current_state", "UNINITIALIZED")

    def get_icon(self, state: str = None) -> str:
        """Get icon for state."""
        if state is None:
            state = self.get_current_state()
        return STATE_ICONS.get(state, "📍")

    def transition_to(self, new_state: str, force: bool = False) -> Tuple[bool, str]:
        """Transition to a new state. Returns (success, message).

        Validates the transition against the state machine's transition matrix.
        State is persisted to the WM file if one exists.

        Args:
            new_state: The target state to transition to
            force: If True, skip validation (use with caution)

        Returns:
            Tuple of (success, message). If validation fails, success=False
            and message contains the blocking reason.
        """
        old_state = self.get_current_state()

        # Validate the transition unless forced
        if not force:
            if old_state == "WF_CLARIFY":
                allowed = clarify_allowed_targets(self.state.get("clarify_entered_from"))
                if new_state not in allowed:
                    return False, (
                        f"BLOCKED: WF_CLARIFY may only return to {allowed}, not {new_state}. "
                        f"Use --force to override."
                    )
            else:
                is_valid, error_msg = is_valid_transition(old_state, new_state)
                if not is_valid:
                    return False, error_msg

            loop_block = self._check_loop_guard(old_state, new_state)
            if loop_block is not None:
                return False, loop_block

            claims_block = self._check_doc_claims_gate(new_state)
            if claims_block is not None:
                return False, claims_block

        oscillation_warning = None
        if not force:
            oscillation_warning = self._detect_oscillation_warning(old_state, new_state)

        # Update in-memory state
        self.state["previous_state"] = old_state
        # clarify_entered_from tracks the caller state across the CLARIFY
        # gate. Set it on entry, clear it on exit (from either CLARIFY
        # itself, or leaving a stale value behind if CLARIFY was skipped via
        # --force). Persisted below (write_working_memory_state /
        # write_state_file) since every hook process rebuilds StateManager
        # from disk — an in-memory-only stamp is invisible to the next hook.
        clarify_entered_from_write = "__unset__"
        if new_state == "WF_CLARIFY":
            self.state["clarify_entered_from"] = old_state
            clarify_entered_from_write = old_state
        elif old_state == "WF_CLARIFY":
            self.state["clarify_entered_from"] = None
            clarify_entered_from_write = None
        self.state["current_state"] = new_state

        # Handle plan mode
        if new_state in PLAN_MODE_STATES and not self.state.get("plan_mode"):
            self.state["plan_mode"] = True
            self.state["plan_mode_entries"] = self.state.get("plan_mode_entries", 0) + 1
            self.state["plan_mode_reason"] = new_state
        elif new_state in EXIT_PLAN_MODE_STATES and self.state.get("plan_mode"):
            self.state["plan_mode"] = False
            self.state["plan_mode_reason"] = None

        # Save state — decoupled state file is authoritative
        sid = self.session_id or self.state.get("session_id")

        # Entering classification starts a NEW task: invalidate the per-task
        # sweep sentinel so the edit gate re-arms for follow-up tasks.
        if new_state == 'WF_CLASSIFY':
            clear_sweep_sentinel(sid)

        suffix = f" ⚠️ {oscillation_warning}" if oscillation_warning else ""

        if self.wm_filepath:
            if write_working_memory_state(self.cwd, self.wm_filepath, new_state, session_id=sid,
                                           clarify_entered_from=clarify_entered_from_write):
                return True, f"Transition: {old_state} → {new_state}{suffix}"
            else:
                return False, f"Failed to save state transition to WM"
        elif sid:
            # No WM yet — write state file only
            if write_state_file(sid, new_state, prev_state=old_state,
                                 clarify_entered_from=clarify_entered_from_write):
                return True, f"Transition: {old_state} → {new_state} (state file only){suffix}"
            return False, "Failed to write state file"
        else:
            # No WM and no session — in-memory only
            return True, f"Transition: {old_state} → {new_state} (in-memory, no WM yet){suffix}"

    def _get_state_events(self) -> List[dict]:
        """Best-effort read of this session's 'state' events from the stream.

        Returns [] (never raises) if there is no session, no stream module,
        or no stream file yet — the loop guard degrades to a no-op rather
        than guessing at session identity.
        """
        sid = self.session_id or self.state.get("session_id")
        if not sid:
            return []
        try:
            from .stream import get_stream_path
            path = get_stream_path(sid)
        except Exception:
            return []
        if not os.path.exists(path):
            return []
        events = []
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError):
                        continue
        except IOError:
            return []
        return events

    def _check_loop_guard(self, old_state: str, new_state: str) -> Optional[str]:
        """Refuse the transition if this edge's loop cap is exceeded.

        Returns the refusal message when the cap is exceeded, else None — a
        None result covers both "within cap" and "guard unavailable" (no
        session events, no loop_guard module, no caps declared): the guard
        degrades to a no-op rather than guessing and blocking a transition it
        cannot actually verify.
        """
        try:
            from . import loop_guard
        except Exception:
            return None
        events = self._get_state_events()
        if not events:
            return None
        caps = load_loop_caps()
        if not caps:
            return None
        ok, _count, _cap, message = loop_guard.check_loop_cap(events, old_state, new_state, caps)
        if not ok:
            return message
        return None

    def _check_doc_claims_gate(self, new_state: str) -> Optional[str]:
        """Refuse a WF_VERIFY / WF_DONE transition while '## Doc Claims Used'
        rows are still pending.

        Reads this session's WM file and parses the Doc Claims ledger via
        core.doc_claims (rows: 'mem:<name> → <claim> → pending|confirmed|
        corrected → <true value>'). Any row still 'pending' — or 'corrected'
        with no recorded true value — blocks the transition: every doc claim
        used during the task must be confirmed against code or corrected
        (edit the source memory, recording the true value) before
        verification/completion. Missing WM file or missing section = no
        rows = pass (zero-cost when the ledger is unused). Same refusal
        mechanism as the loop-cap guard — runs only in the validated branch
        of transition_to, so --force overrides it.

        Lazy import: doc_claims may be absent mid-development, in which case
        the gate degrades to a no-op. A real parse error propagates (fail
        fast).

        Returns the refusal message, or None to allow the transition.
        """
        if new_state not in ("WF_VERIFY", "WF_DONE"):
            return None
        if not self.wm_filepath or not os.path.exists(self.wm_filepath):
            return None
        try:
            from .doc_claims import blocking_claims
        except ImportError:
            return None
        with open(self.wm_filepath, 'r') as f:
            wm_content = f.read()
        blocked = blocking_claims(wm_content)
        if not blocked:
            return None
        rows = "; ".join(
            f"mem:{row['name']} → {row['claim']} → {row['status']}"
            for row in blocked)
        return (
            f"Doc Claims Used has {len(blocked)} blocking row(s): {rows}. "
            "Confirm or correct each claim (edit the source memory; a "
            "'corrected' row MUST record the true value) before VERIFY/DONE."
        )

    def _detect_oscillation_warning(self, old_state: str, new_state: str) -> Optional[str]:
        """Best-effort oscillation warning for the transition about to happen.

        Included as a warning suffix on success, never blocks. Looks at the
        prospective edge appended to the real event history.
        """
        try:
            from . import loop_guard
        except Exception:
            return None
        events = self._get_state_events()
        prospective = events + [{"type": "state", "from_s": old_state, "to_s": new_state}]
        try:
            return loop_guard.detect_oscillation(prospective)
        except Exception:
            return None

    def increment_edits(self, edited_file: str = None) -> int:
        """Increment in-memory edit counter.

        Persistent edit tracking is handled by the stream layer.

        Args:
            edited_file: Optional path to the file that was edited (unused,
                        kept for call-site compatibility)

        Returns:
            New edit count
        """
        self.state["edits_since_checkpoint"] = \
            self.state.get("edits_since_checkpoint", 0) + 1
        return self.state["edits_since_checkpoint"]

    def reset_edit_counter(self):
        """Reset in-memory edit counter after checkpoint."""
        self.state["edits_since_checkpoint"] = 0

    def should_checkpoint(self, threshold: int = 3) -> bool:
        """Check if checkpoint is needed based on edit count."""
        return self.state.get("edits_since_checkpoint", 0) >= threshold

    def set_working_memory(self, filename: str):
        """Set the active working memory file and reload state from it."""
        self.wm_filename = filename
        paths_module = __import__('swe_hooks.core.config', fromlist=['get_paths'])
        paths = paths_module.get_paths(self.cwd)
        self.wm_filepath = f"{paths['serena_memories']}/{filename}.md"
        self.state["working_memory_file"] = filename
        
        # Reload state from the new WM file
        state_data, _ = read_working_memory_state(self.cwd, filename)
        if state_data:
            self.state["current_state"] = state_data.get("current_state", self.state["current_state"])
            self.state["session_id"] = state_data.get("session_id")
            self.state["feature_keys"] = state_data.get("feature_keys", [])

    def get_working_memory(self) -> Optional[str]:
        """Get the active working memory filename."""
        return self.wm_filename or self.state.get("working_memory_file")

    def is_plan_mode(self) -> bool:
        """Check if currently in plan mode."""
        return self.state.get("plan_mode", False)

    def save(self) -> bool:
        """Save current state to WM file and/or state file."""
        sid = self.session_id or self.state.get("session_id")
        if self.wm_filepath:
            return write_working_memory_state(
                self.cwd,
                self.wm_filepath,
                self.state.get("current_state", "WF_INIT"),
                session_id=sid
            )
        elif sid:
            return write_state_file(
                sid,
                self.state.get("current_state", "WF_INIT")
            )
        return False  # No WM or session to save to
