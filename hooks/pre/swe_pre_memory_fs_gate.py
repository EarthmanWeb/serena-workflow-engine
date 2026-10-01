#!/usr/bin/env python3
"""PreToolUse hook for Bash/Grep/Glob/Read — DENY filesystem access to Serena
memory stores; redirect to the Serena memory MCP tools.

Agents sometimes read/search `.serena/memory(ies)/` through the filesystem
(`cd .serena/memory && grep -rlnE ... . | head`, `head -15 index/X.md` with
cwd inside the memory dir, `sed -n '1,20p' ref/X.md`) instead of the Serena
tools (read_memory/list_memories/search_memories_by_name/
search_memories_by_front_matter/search_for_pattern/write_memory/edit_memory).
That bypasses frontmatter/indexing/sync behavior those tools maintain and
defeats memory aliasing (mem:dom/DOM_SWE_MEMORY_PATHS). This gate denies the
raw-FS path and points at the Serena equivalent.

Detection: hooks/swe_hooks/core/memory_fs.py's tool_memory_access() — see
that module for the full Bash-classification contract (effective-cwd
tracking, FS_CMDS, redirection targets, perl -i, inline interpreters).

Exemptions (fail-open by design):
  - Project setup not complete or workflow-bypassed
    (core.config.resolve_setup_state) — unmanaged/bypassed projects get no
    enforcement from this gate either.
  - A spawned `swe-init-agent` (payload agent_type is `swe-init-agent` or
    ends with `:swe-init-agent`) — bootstrap needs raw FS access before
    Serena reconnects after `/swe-init`.
Applies to every other caller, main agent AND subagent alike — unlike the
docs-first gate, there is no spawned-agent carve-out here: a subagent reading
memory files off disk is exactly as wrong as the orchestrator doing it.
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_block
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.config import get_project_root, resolve_setup_state
    from swe_hooks.core import memory_fs
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")


def _is_init_agent(input_data: dict) -> bool:
    """True when this call was made by a spawned `swe-init-agent`.

    Bootstrap needs raw filesystem access before Serena has reconnected —
    the only spawned-agent carve-out this gate grants. Matches an exact
    `swe-init-agent` or a `<anything>:swe-init-agent` qualified name.
    """
    for key in ('agent_type', 'agentType'):
        val = input_data.get(key)
        if isinstance(val, str) and val.strip():
            v = val.strip()
            if v == 'swe-init-agent' or v.endswith(':swe-init-agent'):
                return True
    return False


def _derive_memory_name(path: str, cwd: str) -> str:
    """Best-effort logical memory name for a single-file target, for the
    deny message's `read_memory(...)` suggestion. '' if not derivable."""
    if not path:
        return ''
    expanded = path
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd or os.getcwd(), expanded)
    normalized = os.path.normpath(expanded).replace('\\', '/')
    for marker in ('/.serena/memory/', '/.serena/memories/'):
        idx = normalized.find(marker)
        if idx != -1:
            rel = normalized[idx + len(marker):]
            if rel.endswith('.md'):
                return rel[:-3]
    return ''


def _target_path(tool_name: str, tool_input: dict) -> str:
    tool_input = tool_input or {}
    if tool_name == 'Bash':
        return ''
    for field in ('file_path', 'notebook_path', 'path'):
        val = tool_input.get(field)
        if val:
            return str(val)
    return ''


def build_deny_message(tool_name: str, tool_input: dict, cwd: str) -> str:
    lines = [
        "\U0001f6d1 [memory-fs] Filesystem access to Serena memory stores is "
        "blocked — use the Serena memory tools:",
    ]
    target = _target_path(tool_name, tool_input)
    name = _derive_memory_name(target, cwd)
    if name:
        lines.append(
            f'  read one memory  -> mcp__plugin_swe_serena__read_memory(memory_name="{name}")')
    else:
        lines.append(
            '  read one memory  -> mcp__plugin_swe_serena__read_memory(memory_name="<topic>/<NAME>")')
    lines.append(
        '  list a topic     -> mcp__plugin_swe_serena__list_memories(topic="<prefix>")')
    lines.append(
        '  find by name     -> mcp__plugin_swe_serena__search_memories_by_name(query="<terms>")')
    lines.append(
        '  find by subject  -> mcp__plugin_swe_serena__search_memories_by_front_matter(query="<terms>")')
    lines.append(
        '  search body text -> mcp__plugin_swe_serena__search_for_pattern('
        'substring_pattern="<pattern>", relative_path=".serena/memory")')
    lines.append(
        '  write/edit       -> mcp__plugin_swe_serena__write_memory(...) / '
        'mcp__plugin_swe_serena__edit_memory(...)')
    lines.append(
        '  Working Memory   -> mcp__plugin_swe_swe-wm__swe_wm_read(...)')
    lines.append(
        "Serena tool missing or failing → reconnect Serena (/mcp). NEVER "
        "fall back to Bash/Grep/Glob/Read on memory files.")
    return "\n".join(lines)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = get_input_field(input_data, 'tool_name', default='')
        tool_input = input_data.get('tool_input', {}) or {}
        cwd = get_input_field(input_data, 'cwd', default=os.getcwd())

        if not memory_fs.tool_memory_access(tool_name, tool_input, cwd):
            output_empty()
            return

        try:
            if resolve_setup_state(get_project_root()).get('bypassed'):
                output_empty()
                return
            if not resolve_setup_state(get_project_root()).get('initialized'):
                output_empty()
                return
        except Exception:
            output_empty()
            return

        if _is_init_agent(input_data):
            output_empty()
            return

        output_block(build_deny_message(tool_name, tool_input, cwd))

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                         "additionalContext": f"Memory-fs gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == '__main__':
    main()
