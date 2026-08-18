#!/usr/bin/env python3
"""PostToolUse hook for read_memory - State transitions.

When a WF_* memory is read, this hook transitions the workflow state.
Uses session isolation to ensure state changes only affect the current session.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty, output_status
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.state_manager import StateManager, STATE_ICONS, is_forward_read_transition
    from swe_hooks.core.session import extract_session_id, get_project_root, find_working_memory_for_session
    from swe_hooks.core.config import append_transition_to_wm, write_state_file, resolve_installed_plugin, resolve_plugin_root
    from swe_hooks.core.stream import (
        get_stream_path, append_event, get_sentinel_path,
        collect_values_since_task_start,
    )
    from datetime import datetime
    import re
    import time
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e)


# Memory names in search results look like "dir/NAME" (e.g.
# "feedback/FEEDBACK_DOCS_FIRST_ALWAYS"). Matched anywhere in the serialized
# tool result; normalization happens in _extract_memory_names.
MEMORY_NAME_RE = re.compile(r'\b[a-z][a-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*')

# Explicit memory links INSIDE a read memory's content: `mem:dir/NAME` and
# `[[dir/NAME]]`. Bare dir/NAME mentions are NOT links.
MEMORY_LINK_RE = re.compile(
    r'(?:mem:|\[\[)\s*([a-z][a-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*?)\s*(?:\]\]|(?=[^A-Za-z0-9_./-])|$)')

# Topics excluded from related-link tracking — workflow machinery and the
# WF_CLASSIFY 4d sweep exclusions (never loaded as general context).
LINK_EXCLUDED_PREFIXES = (
    'wf/', 'claude/', 'spec/', 'report/', 'research/', 'project/',
    'templates/',
)


def _related_links(text: str) -> set:
    """Normalized memory names explicitly linked from read memory content."""
    from swe_hooks.core.stream import normalize_memory_name
    if not text:
        return set()
    links = set()
    for match in MEMORY_LINK_RE.findall(str(text)):
        name = normalize_memory_name(match)
        if not name.startswith(LINK_EXCLUDED_PREFIXES):
            links.add(name)
    return links


def _unread_related(memory_name: str, content: str, read_names: set) -> set:
    """Related links of a just-read memory not yet read this task."""
    from swe_hooks.core.stream import normalize_memory_name
    return (_related_links(content)
            - set(read_names)
            - {normalize_memory_name(memory_name)})


def _extract_memory_names(text: str) -> set:
    """Extract normalized memory names from a search tool result blob."""
    from swe_hooks.core.stream import normalize_memory_name
    if not text:
        return set()
    return {normalize_memory_name(m) for m in MEMORY_NAME_RE.findall(str(text))}


def _search_credit(hit_names: set, read_names: set):
    """Decide docs-first credit for a memory search.

    Returns (credit, new_names). Credit is granted when the search surfaced
    NOTHING the agent has not already read this task — either zero hits
    (nothing documented → exploring source is legitimate) or every hit already
    read (re-search confirming the same authoritative docs). NEW names mean
    unread documentation was just surfaced: no credit until it is read.
    """
    new_names = set(hit_names) - set(read_names)
    return (len(new_names) == 0, new_names)


def create_feature_sentinel(session_id: str, gate_name: str) -> bool:
    """Create a sentinel file for a feature gate.

    Pattern: .serena/streams/.{gate_name}_feature_{session_id}
    Used by: FEATURE_TESTS (test gate).
    """
    if not session_id:
        return False
    try:
        stream_dir = get_stream_path(session_id).rsplit('/', 1)[0]
        sentinel = os.path.join(stream_dir, f'.{gate_name}_feature_{session_id}')
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        open(sentinel, 'w').close()
        return True
    except IOError:
        return False


def _get_plugin_version() -> str:
    """Report the AUTHORITATIVE installed plugin version.

    Resolution order:
    1. installed_plugins.json `version` (source of truth — follows updates even
       if this process was launched under an older ${CLAUDE_PLUGIN_ROOT}).
    2. plugin.json at the installed root (resolve_plugin_root()).
    3. plugin.json under launch-time CLAUDE_PLUGIN_ROOT / derived path (dev).

    Reading directly from the launch-time CLAUDE_PLUGIN_ROOT (the old behaviour)
    reports a stale version after an in-place update, because a long-lived hook
    process keeps its launch root. The installed manifest does not.
    """
    # 1. Authoritative version straight from the install manifest.
    _, version = resolve_installed_plugin()
    if version:
        return version

    # 2/3. Fall back to plugin.json at the installed root, else launch root.
    plugin_root = resolve_plugin_root()
    if plugin_root:
        plugin_json = os.path.join(plugin_root, '.claude-plugin', 'plugin.json')
    else:
        # Derive: post/ -> hooks/ -> plugin root
        plugin_json = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            '.claude-plugin', 'plugin.json'
        )
    try:
        with open(plugin_json) as f:
            return json.load(f).get('version', '')
    except (IOError, json.JSONDecodeError, ValueError):
        return ''


def _get_continuation(current_state: str, session_id: str = None) -> str:
    """Get a one-line continuation directive for the current workflow state.

    Prevents mid-step stalls by reminding the agent what to do next.
    Only fires for states where stalls have been observed. For WF_CLASSIFY the
    directive embeds the exact one-pass WM call — the observed failure mode is
    the agent omitting session_id or serializing legacy per-section calls.
    """
    sid = f'session_id="{session_id}"' if session_id else 'session_id="<id>"'
    directives = {
        "WF_CLASSIFY": (
            "Load ALL FEATURE_[KEY] + supporting DOM_*/SYS_*/SPEC_* memories "
            f"→ ONE swe_wm_update call ({sid}, sections=[Affected Features "
            "with '**Memories loaded**:' as PLAIN comma-separated names — no "
            "annotations, no wf/*+claude/*]) → route to next step"),
        "WF_ARCH_REVIEW": "Complete architecture review → present plan → route to WF_EXECUTE",
        "WF_EXECUTE": "Continue implementation → checkpoint at 3+ edits → WF_VERIFY when done",
        "WF_RESEARCH": "Continue investigation → record findings → route when complete",
        "WF_VERIFY": "Complete verification checks → update WM → read wf/WF_DONE when all clean",
        "WF_DONE": "Update WM with final status → summarize to user → end session",
    }
    d = directives.get(current_state)
    return f"⏩ CONTINUE ({current_state}): {d}" if d else ""


def _bootstrap_session_at_classify(cwd, session_id):
    """Create WM + state file + init sentinel when the init chain reaches
    WF_CLASSIFY. Restores the bootstrap that WF_START used to perform (v3),
    now bound to the v4 post-init entry state. Idempotent: callers guard on
    sentinel absence. Mirrors create_wm_and_sentinel() in the prompt hook.
    """
    project_root = get_project_root()
    wm_filename = f"WM_{session_id}.md"
    wm_filepath = os.path.join(project_root, ".serena", "memories", wm_filename)

    wm_content = f"""# Working Memory: Session {session_id}

## Session
- **ID**: {session_id}
- **Task**: (awaiting classification)
- **Started**: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Workflow Context
**Current State**: WF_CLASSIFY
**Previous State**: WF_INIT
**Session ID**: {session_id}

## Task Context
- **Feature(s)**: (to be determined)
- **Complexity**: (to be determined)

## Progress Tracking
### Pending
- [ ] Classify task

## Requirements
(to be determined from user request)

## Implementation Notes
(none yet)
"""
    try:
        os.makedirs(os.path.dirname(wm_filepath), exist_ok=True)
        with open(wm_filepath, 'w', encoding='utf-8') as f:
            f.write(wm_content)
    except IOError:
        pass

    # Decoupled state file — advance WF_INIT → WF_CLASSIFY.
    write_state_file(session_id, 'WF_CLASSIFY', prev_state='WF_INIT')

    # Session start stream event.
    try:
        append_event(get_stream_path(session_id), 'session_start', s=session_id)
    except Exception:
        pass

    # Init sentinel — unlocks the pre-init gate for this session.
    sentinel = get_sentinel_path(session_id)
    try:
        os.makedirs(os.path.dirname(sentinel), exist_ok=True)
        sentinel_data = {
            "session_id": session_id,
            "wm_file": wm_filename.replace('.md', ''),
            "validated_at": int(time.time()),
        }
        with open(sentinel, 'w') as sf:
            json.dump(sentinel_data, sf, separators=(',', ':'))
    except IOError:
        pass


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())
        tool_name = get_input_field(input_data, 'tool_name', default='')
        memory_name = get_input_field(input_data, 'tool_input', 'memory_name', default='')
        tool_result = get_input_field(input_data, 'tool_result', default='')
        # Bare name without directory prefix (e.g. "wf/WF_CLASSIFY" -> "WF_CLASSIFY")
        bare_name = memory_name.rsplit('/', 1)[-1] if memory_name else ''

        # Build input echo prefix for all output paths
        _in_label = f"[IN: memory_name=\"{memory_name}\"]" if memory_name else ""

        # Extract session ID early (needed for continuation directives)
        transcript_path = get_input_field(input_data, 'transcript_path', default='')
        session_id = extract_session_id(transcript_path)

        # Memory-name/front-matter searches: credit is NAME-AWARE. A search
        # whose hits are all already read this task (or that finds nothing)
        # counts as consulting docs — docread credit, budget refill. A search
        # that surfaces UNREAD memories is discovery, not research: no credit
        # until the surfaced docs are actually read.
        if 'search_memories' in tool_name:
            stream_path = get_stream_path(session_id)
            raw_result = tool_result or get_input_field(
                input_data, 'tool_response', default='')
            hits = _extract_memory_names(str(raw_result))
            read_names = collect_values_since_task_start(stream_path)
            credit, new_names = _search_credit(hits, read_names)
            if credit:
                try:
                    append_event(stream_path, 'docread', s=session_id,
                                 name='memory-search')
                except Exception:
                    pass
                output_status("🔎 Memory search logged — docs-first credit "
                              "(no unread docs surfaced)")
            else:
                try:
                    append_event(stream_path, 'docsearch', s=session_id,
                                 new=sorted(new_names))
                except Exception:
                    pass
                listing = ", ".join(sorted(new_names))
                output_status(
                    "🔎 Discovery surfaced UNREAD docs — NO docs-first credit "
                    f"until they are read: {listing}. read_memory each before "
                    "proceeding; reading them grants the credit.")
            return

        # Consulting documentation (any list_memories / read_memory) resets the
        # wide-search streak tracked by swe_post_search_docs_hint.py and records
        # WHICH memory was read (sweep-gate verification). Best-effort.
        try:
            append_event(get_stream_path(session_id), 'docread', s=session_id,
                         name=memory_name or tool_name)
        except Exception:
            pass

        # Related-links surfacing (mirrors the search rule for reads): a read
        # whose content links memories unread this task records them as
        # pending discovery — the docs-first gate lists them as the designated
        # next reads, and re-reading this same memory will not refill budget.
        pending_msg = ''
        if memory_name and not bare_name.startswith('WF_'):
            raw_result = tool_result or get_input_field(
                input_data, 'tool_response', default='')
            try:
                read_names = collect_values_since_task_start(
                    get_stream_path(session_id))
                unread = _unread_related(memory_name, str(raw_result), read_names)
            except Exception:
                unread = set()
            if unread:
                try:
                    append_event(get_stream_path(session_id), 'docpending',
                                 s=session_id, new=sorted(unread))
                except Exception:
                    pass
                pending_msg = (
                    "📚 Related docs linked here, UNREAD this task: "
                    + ", ".join(sorted(unread))
                    + " — deferred refs (tiered 4d loading). Read one the moment "
                    "it becomes relevant to what you change/inspect (on-miss "
                    "expansion), not preemptively; re-reading an already-read "
                    "memory does not refill the docs budget.")

        # Handle list_memories calls (no memory_name) — inject continuation
        if 'list_memories' in tool_name:
            state_mgr = StateManager(cwd, session_id=session_id)
            current = state_mgr.get_current_state()
            directive = _get_continuation(current, session_id)
            if directive:
                output = HookOutput(event_name="PostToolUse")
                output.add_message("📋 Memories listed")
                output.add_message("")
                output.add_message(directive)
                output.output_and_exit()
            output_status(f"📋 Memories listed {_in_label}")
            return

        # Handle FEATURE_TESTS read - create sentinel for test gate
        if bare_name == 'FEATURE_TESTS':
            create_feature_sentinel(session_id, 'test')
            output = HookOutput(event_name="PostToolUse")
            output.add_message(f"📖 Read: {memory_name} {_in_label}")
            if pending_msg:
                output.add_message(pending_msg)
            output.output_and_exit()
            return

        # Non-WF_* memories: log read + inject continuation directive
        if not bare_name or not bare_name.startswith('WF_'):
            state_mgr = StateManager(cwd, session_id=session_id)
            current = state_mgr.get_current_state()
            directive = _get_continuation(current, session_id)

            if directive or pending_msg:
                output = HookOutput(event_name="PostToolUse")
                output.add_message(f"📖 Read: {memory_name or 'unknown'} {_in_label}")
                if pending_msg:
                    output.add_message(pending_msg)
                if directive:
                    output.add_message("")
                    output.add_message(directive)
                output.output_and_exit()

            output_status(f"📖 Read: {memory_name or 'unknown'} {_in_label}")
            return

        # WF_* read = FORWARD-GATED TRANSITION (restored pre-v4 flow, fixed).
        # Reading the next workflow memory navigates the FSM forward — the
        # natural "read your way through the workflow" behavior. The old bug was
        # that ANY matrix-valid read advanced state, so reading-ahead/backward to
        # INSPECT a memory jumped the FSM to the wrong place. Fix: a read advances
        # ONLY on a forward move (is_forward_read_transition); inspecting,
        # reading-ahead, or backward reads are logged as "ON STEP" but do NOT move
        # the FSM. Transitions can also still be driven by the prompt-intent hook.
        state_mgr = StateManager(cwd, session_id=session_id)

        output = HookOutput(event_name="PostToolUse")
        icon = STATE_ICONS.get(bare_name, '📍')
        current = state_mgr.get_current_state()
        version = _get_plugin_version()
        ver_tag = f" (v{version})" if version else ""

        label = f"{icon} ON STEP: {bare_name}{ver_tag}"
        labelled = False  # ensure exactly one "ON STEP" line is emitted

        # INIT-CHAIN COMPLETION (special bootstrap). v4 removed WF_START; the WM +
        # init sentinel used to be created on transition to WF_START during init.
        # The init chain now ends by reading wf/WF_CLASSIFY. When wf/WF_CLASSIFY is
        # read while still at WF_INIT and the session is not yet initialized,
        # bootstrap it here: create WM + sentinel and advance WF_INIT→WF_CLASSIFY.
        if bare_name == 'WF_CLASSIFY' and current in ('WF_INIT', 'UNINITIALIZED'):
            sentinel = get_sentinel_path(session_id) if session_id else None
            if session_id and sentinel and not os.path.exists(sentinel):
                _bootstrap_session_at_classify(cwd, session_id)
                current = 'WF_CLASSIFY'
                output.add_message(label)
                labelled = True

        # FORWARD READ TRANSITION — restored, gated read-driven advance.
        if not labelled and bare_name != current:
            should, _reason = is_forward_read_transition(current, bare_name)
            if should:
                success, msg = state_mgr.transition_to(bare_name)
                output.add_message(label)
                labelled = True
                if success:
                    append_event(get_stream_path(session_id), 'state',
                                 from_s=current, to_s=bare_name, s=session_id)
                    if state_mgr.wm_filepath:
                        append_transition_to_wm(state_mgr.wm_filepath, current, bare_name)
                    current = bare_name
                    output.add_message(msg)
                else:
                    output.add_message(f"ℹ️ Note: {msg}")
            else:
                # Inspecting / reading-ahead — log the step, do NOT move the FSM.
                output.add_message(f"{label} (inspecting — no transition)")
                labelled = True

        if not labelled:
            output.add_message(label)

        directive = _get_continuation(current, session_id)
        if directive:
            output.add_message("")
            output.add_message(directive)

        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"Post-read error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
