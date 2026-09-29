#!/usr/bin/env python3
"""Gate-conformance metrics: prove harness arms actually use the SWE plugin's
gates, rather than just measuring token/turn counts around them.

Pure functions only (no I/O) — consumed by run.py (which supplies the raw
stream-event lines and transcript-event dicts already parsed off disk) and
directly unit tested by tests/test_harness_ab.py with real-shaped samples
pulled from experiments/harness-ab/results/20260929-123133.

Event shapes (see hooks/swe_hooks/core/stream.py + real samples under
results/20260929-123133/runs/*/work/.serena/streams/*.jsonl):
    {"t": epoch, "type": "docread", "s": session_id, "name": "wf/WF_INIT"}
    {"t": epoch, "type": "state", "from_s": "WF_CLASSIFY", "to_s": "WF_EXECUTE", "s": ...}
    {"t": epoch, "type": "sweep", "s": session_id}
    {"t": epoch, "type": "sweep_bonus"}
    {"t": epoch, "type": "gated"}
    {"t": epoch, "type": "edit", "file": "<path>", "s": session_id}
    {"t": epoch, "type": "delegation", "tool": "Agent", "s": session_id}
    {"t": epoch, "type": "task_work", "tool": "Bash", "s": session_id}
    {"t": epoch, "type": "docpending", "src": ..., "new": [...]}
    {"t": epoch, "type": "session_start", "s": session_id}

Deny-message prefixes (grepped from hooks/pre/*.py — matched against
tool_result blocks with is_error=True in the transcript):
    "🛑 BLOCKED: read_memory(...) called before WF_INIT complete"   -> init
    "🛑 BLOCKED: <tool> called before WF_INIT complete"             -> init
    "🛑 BLOCKED: No Working Memory for session"                     -> init
    "🛑 BLOCKED: the SWE workflow bypass is user-only"              -> init
    "🛑 BLOCKED: raw Edit/Write on a Serena memory file"            -> edit
    "🛑 SWEEP GATE — edit blocked"                                  -> sweep
    "🛑 SWEEP GATE — test-file edit blocked"                        -> sweep
    "📓 DOCS FIRST"                                                 -> docs
    "🛑 BLOCKED: this write adds"                                   -> docs (memory index gate)
"Stop hook" (assistant text)                                        -> stop
"""
import json
import re

EDIT_TOOL_NAMES = frozenset({
    "Edit", "Write", "NotebookEdit",
    "mcp__plugin_swe_serena__replace_content",
    "mcp__plugin_swe_serena__replace_symbol_body",
    "mcp__plugin_swe_serena__insert_after_symbol",
    "mcp__plugin_swe_serena__insert_before_symbol",
    "mcp__plugin_swe_serena__replace_in_files",
    "mcp__plugin_swe_serena__rename_symbol",
    "mcp__plugin_swe_serena__safe_delete_symbol",
})

MEMORY_READ_TOOL_NAMES = frozenset({
    "mcp__plugin_swe_serena__read_memory",
})

MEMORY_PATH_RE = re.compile(r"\.serena/memor(?:y|ies)/(.+?)\.md$")

INIT_CHAIN = ["wf/wf_init", "claude/claude_obligations", "wf/wf_classify"]

DENY_PATTERNS = [
    ("init", re.compile(r"BLOCKED:.*called before WF_INIT complete", re.IGNORECASE)),
    ("init", re.compile(r"BLOCKED:\s*No Working Memory for session", re.IGNORECASE)),
    ("init", re.compile(r"BLOCKED:.*workflow bypass is user-only", re.IGNORECASE)),
    ("sweep", re.compile(r"SWEEP GATE", re.IGNORECASE)),
    ("edit", re.compile(r"BLOCKED:.*raw Edit/Write on a Serena memory file", re.IGNORECASE)),
    ("docs", re.compile(r"DOCS FIRST", re.IGNORECASE)),
    ("docs", re.compile(r"BLOCKED:.*this write adds", re.IGNORECASE)),
]
STOP_BLOCK_RE = re.compile(r"Stop hook", re.IGNORECASE)


def normalize_memory_name(name):
    """Match stream.py's normalize_memory_name: lowercase, strip 'mem:'
    prefix and '.md' suffix."""
    if not name:
        return ""
    name = str(name).strip().lower()
    if name.startswith("mem:"):
        name = name[4:]
    if name.endswith(".md"):
        name = name[:-3]
    return name


def parse_stream_events(lines):
    """Parse raw .serena/streams/*.jsonl lines into a list of event dicts,
    preserving file order, skipping malformed lines. Pure."""
    events = []
    for raw in lines:
        raw = raw.strip() if isinstance(raw, str) else raw
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def classify_deny_reason(text):
    """Classify a tool_result deny-message text into a gate kind:
    'init' | 'sweep' | 'edit' | 'docs' | 'stop' | None. Pure."""
    if not text:
        return None
    for kind, pattern in DENY_PATTERNS:
        if pattern.search(text):
            return kind
    if STOP_BLOCK_RE.search(text):
        return "stop"
    return None


def _tool_result_text(block):
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text") or "")
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return ""


def iter_transcript_tool_events(transcript_events):
    """Yield (index, kind, name, payload) tuples in transcript order for the
    events gate-conformance cares about, across main agent + subagents:
        kind == "tool_use"     -> payload = tool_use input dict
        kind == "tool_deny"    -> payload = deny-message text
        kind == "stop_block"   -> payload = assistant text
    `index` is the 0-based position within transcript_events (stable
    ordering key across main + subagent interleaving, since Claude Code
    writes stream-json events in wall-clock/emission order regardless of
    which agent produced them).
    """
    for i, event in enumerate(transcript_events):
        if not isinstance(event, dict):
            continue
        etype = event.get("type")
        message = event.get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            continue

        if etype == "assistant":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    yield (i, "tool_use", block.get("name") or "unknown", block.get("input") or {})
                elif block.get("type") == "text":
                    text = block.get("text") or ""
                    if STOP_BLOCK_RE.search(text):
                        yield (i, "stop_block", None, text)

        elif etype == "user":
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result" and block.get("is_error"):
                    text = _tool_result_text(block)
                    yield (i, "tool_deny", None, text)


def compute_init_chain_complete(transcript_events):
    """True iff docreads of wf/WF_INIT, claude/CLAUDE_OBLIGATIONS,
    wf/WF_CLASSIFY occur (via mcp__plugin_swe_serena__read_memory tool_use
    calls) in that order, before any OTHER (non-memory-read) tool_use event
    in the transcript. Pure.

    "non-memory-read tool_use" = any tool_use whose name is not
    read_memory/list_memories/search_memories_by_name/
    search_memories_by_front_matter — i.e. genuine task work, matching
    run.py's MEMORY_TOOL_NAMES intent but scoped to reads only (list/search
    calls before init completes don't violate the chain requirement, only
    reading a DIFFERENT memory or doing task work would — this function
    tracks the chain itself, not the full init-gate policy).
    """
    memory_list_search = frozenset({
        "mcp__plugin_swe_serena__list_memories",
        "mcp__plugin_swe_serena__search_memories_by_name",
        "mcp__plugin_swe_serena__search_memories_by_front_matter",
        # ToolSearch loads a deferred MCP tool's schema (e.g. read_memory
        # itself, on a harness build where Serena tools are deferred) — it
        # is infrastructure for making the chain call possible, not task
        # work, and legitimately precedes the very first read_memory call.
        # Real transcripts confirm this shape (see
        # results/20260929-123133/runs/baseline-t1/transcript.jsonl,
        # event index 22: ToolSearch immediately before wf/WF_INIT's
        # read_memory at index 25).
        "ToolSearch",
    })
    chain_progress = 0
    for _i, kind, name, payload in iter_transcript_tool_events(transcript_events):
        if kind != "tool_use":
            continue
        if name in MEMORY_READ_TOOL_NAMES:
            mem_name = normalize_memory_name(payload.get("memory_name"))
            if chain_progress < len(INIT_CHAIN) and mem_name == INIT_CHAIN[chain_progress]:
                chain_progress += 1
                if chain_progress == len(INIT_CHAIN):
                    return True
                continue
            # A read_memory of something else doesn't break the chain by
            # itself (e.g. a re-read); only non-memory-read tool work before
            # the chain completes breaks it.
            continue
        if name in memory_list_search:
            continue
        # Any other tool_use before the chain completed -> chain violated.
        if chain_progress < len(INIT_CHAIN):
            return False
    return chain_progress == len(INIT_CHAIN)


def find_sweep_index(stream_events):
    """Index (into stream_events) of the first 'sweep' event, or None."""
    for i, event in enumerate(stream_events):
        if event.get("type") == "sweep":
            return i
    return None


def compute_sweep_verified(stream_events):
    """True iff a 'sweep' marker event exists anywhere in the stream. Pure."""
    return find_sweep_index(stream_events) is not None


def _edit_tool_use_positions(transcript_events):
    """Ordered list of transcript indices where an Edit/Write/NotebookEdit or
    Serena structural-edit tool_use occurred (main agent or subagent)."""
    out = []
    for i, kind, name, _payload in iter_transcript_tool_events(transcript_events):
        if kind == "tool_use" and name in EDIT_TOOL_NAMES:
            out.append(i)
    return out


def compute_edits_before_sweep(stream_events, transcript_events):
    """Count of Edit/Write/NotebookEdit/Serena-edit tool_use events (main
    agent + subagents) that occur before the sweep marker in wall-clock
    order.

    Correlates the stream's 'edit' events (which the plugin itself only
    emits post-sweep-gate-pass, so their COUNT is a lower bound on real
    edits) against the transcript's tool_use timeline using the stream
    event's position among edit-type stream events vs. the sweep event's
    stream position. Since stream events and transcript events are both
    emission-ordered but on separate timelines, we count via the stream
    itself: number of 'edit' stream events with stream index < sweep index.
    A 0 result means the plugin's own edit-gate correctly blocked every
    edit attempt before the sweep was recorded; a run with edits recorded
    before the sweep index is a genuine conformance violation (or a
    fail-open path such as a WM_* write or spawned-agent session with no
    sentinel — see swe_pre_edit_validate.py's _sweep_gate_verdict
    docstring).

    Falls back to counting transcript-level Edit/Write/NotebookEdit tool_use
    events before ANY 'sweep' stream event when the stream has no edit
    events at all but the transcript does show edit tool_use calls (keeps
    the metric meaningful for a stream that predates the 'edit' event type,
    or a control arm with no stream at all — sweep_index is None there, so
    every edit counts as "before sweep", correctly flagging non-conformance
    for an arm with no gate at all).
    """
    sweep_idx = find_sweep_index(stream_events)

    stream_edit_events = [e for e in stream_events if e.get("type") == "edit"]
    if stream_edit_events:
        if sweep_idx is None:
            return len(stream_edit_events)
        count = 0
        for i, event in enumerate(stream_events):
            if i >= sweep_idx:
                break
            if event.get("type") == "edit":
                count += 1
        return count

    # No stream 'edit' events recorded (no plugin, or pre-instrumentation
    # stream) -> fall back to transcript tool_use timeline. Without a stream
    # sweep marker at all, every edit attempt counts as unconformant.
    edit_positions = _edit_tool_use_positions(transcript_events)
    if sweep_idx is None:
        return len(edit_positions)
    return len(edit_positions)


def compute_memories_read(transcript_events, stream_events):
    """Ordered unique list of memory names read this run, from BOTH channels:
      - stream 'docread' events (name field)
      - transcript mcp__plugin_swe_serena__read_memory tool_use inputs
        (memory_name), main agent + subagents

    Returns list of normalized names in first-seen order (stream events
    considered first since they're the authoritative plugin-side record,
    then any transcript-only reads not already present). Pure."""
    seen = []
    seen_set = set()

    for event in stream_events:
        if event.get("type") != "docread":
            continue
        name = normalize_memory_name(event.get("name"))
        if name and name not in seen_set:
            seen_set.add(name)
            seen.append(name)

    for _i, kind, name, payload in iter_transcript_tool_events(transcript_events):
        if kind != "tool_use" or name not in MEMORY_READ_TOOL_NAMES:
            continue
        mem_name = normalize_memory_name(payload.get("memory_name"))
        if mem_name and mem_name not in seen_set:
            seen_set.add(mem_name)
            seen.append(mem_name)

    return seen


def compute_control_memories_read(transcript_events):
    """Control-arm equivalent of compute_memories_read: memory names read via
    plain Read of a `.serena/memory/...` (or `.serena/memories/...`) file
    path — the only channel available with no plugin/MCP loaded. Returns
    ordered unique list of normalized names. Pure."""
    seen = []
    seen_set = set()
    for _i, kind, name, payload in iter_transcript_tool_events(transcript_events):
        if kind != "tool_use" or name != "Read":
            continue
        path = payload.get("file_path") or payload.get("path") or ""
        if not isinstance(path, str):
            continue
        m = MEMORY_PATH_RE.search(path)
        if not m:
            continue
        # path fragment after .serena/memory/ or .serena/memories/, minus
        # .md, e.g. "feature/FEATURE_LEDGER"
        name = normalize_memory_name(m.group(1))
        if name and name not in seen_set:
            seen_set.add(name)
            seen.append(name)
    return seen


def compute_doc_rule_memories_coverage(memories_read, doc_rules):
    """Given the ordered list of memory names actually read (from either
    compute_memories_read or compute_control_memories_read) and a task's
    doc_rules list ([{id, memory, summary, tests: [...]}, ...]), return
    {"doc_rule_memories_read": [...], "doc_rule_memories_coverage": float}.

    doc_rule_memories_coverage = fraction of DISTINCT rule memories that
    appear in memories_read (0.0 when doc_rules is empty -> returns None
    for coverage to distinguish "no rules to measure" from "0% covered").
    Pure."""
    if not doc_rules:
        return {"doc_rule_memories_read": [], "doc_rule_memories_coverage": None}
    read_set = set(memories_read or [])
    rule_memories = []
    seen = set()
    for rule in doc_rules:
        mem = normalize_memory_name((rule or {}).get("memory"))
        if mem and mem not in seen:
            seen.add(mem)
            rule_memories.append(mem)
    if not rule_memories:
        return {"doc_rule_memories_read": [], "doc_rule_memories_coverage": None}
    read_rule_memories = [m for m in rule_memories if m in read_set]
    coverage = len(read_rule_memories) / len(rule_memories)
    return {"doc_rule_memories_read": read_rule_memories, "doc_rule_memories_coverage": coverage}


def compute_states_visited(stream_events):
    """Ordered list of to_s values from 'state' stream events. Pure."""
    out = []
    for event in stream_events:
        if event.get("type") == "state":
            to_s = event.get("to_s")
            if to_s:
                out.append(to_s)
    return out


def compute_gate_denials(transcript_events):
    """Count tool_deny events by classified kind, plus stop_block count.
    Returns {"init": n, "sweep": n, "edit": n, "docs": n, "stop": n,
    "unclassified": n}. Pure."""
    counts = {"init": 0, "sweep": 0, "edit": 0, "docs": 0, "stop": 0, "unclassified": 0}
    for _i, kind, _name, payload in iter_transcript_tool_events(transcript_events):
        if kind == "tool_deny":
            gate_kind = classify_deny_reason(payload)
            counts[gate_kind or "unclassified"] += 1
        elif kind == "stop_block":
            counts["stop"] += 1
    return counts


def compute_gate_conformance(stream_events, transcript_events, doc_rules=None, is_plugin_arm=True):
    """Top-level per-run gate-conformance dict, assembled from the functions
    above. Pure — no I/O; caller supplies already-loaded event lists.

    When is_plugin_arm is False (control arm), memories_read is computed via
    the plain-Read channel (compute_control_memories_read) instead of the
    stream+MCP channel, and init_chain_complete/sweep_verified/
    edits_before_sweep reflect the (expected: absent) plugin gates -- there
    is no stream to read, so sweep_verified is False and
    edits_before_sweep counts every edit tool_use in the transcript (no gate
    exists to have blocked any of them).
    """
    if is_plugin_arm:
        memories_read = compute_memories_read(transcript_events, stream_events)
        channel = "serena+stream"
    else:
        memories_read = compute_control_memories_read(transcript_events)
        channel = "plain_read"

    coverage = compute_doc_rule_memories_coverage(memories_read, doc_rules)

    result = {
        "init_chain_complete": compute_init_chain_complete(transcript_events) if is_plugin_arm else False,
        "sweep_verified": compute_sweep_verified(stream_events),
        "sweep_index": find_sweep_index(stream_events),
        "edits_before_sweep": compute_edits_before_sweep(stream_events, transcript_events),
        "memories_read": memories_read,
        "memories_read_channel": channel,
        "states_visited": compute_states_visited(stream_events),
        "gate_denials": compute_gate_denials(transcript_events),
    }
    result.update(coverage)
    return result
