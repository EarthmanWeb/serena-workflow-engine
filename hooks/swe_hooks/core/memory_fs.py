"""Shared detection: filesystem access to a Serena memory store.

Agents read/search Serena memories through raw filesystem commands (Bash
grep/cat/head/sed with cwd inside .serena/memory, Read/Grep/Glob targeting a
memory file or tree) instead of the Serena memory MCP tools
(read_memory/list_memories/search_memories_by_name/
search_memories_by_front_matter/write_memory/edit_memory/search_for_pattern).
This module is the pure-function detector used by
hooks/pre/swe_pre_memory_fs_gate.py to DENY that access and by
hooks/pre/swe_pre_edit_validate.py's `_is_raw_memory_write` (symlink-aware
upgrade) — never imported by business logic that should instead just call a
Serena tool.

A Serena memory STORE is `.serena/memory/` or `.serena/memories/` (singular or
plural — see mem:dom/DOM_SWE_INIT_MEMORY_PATHS) — NEVER `.serena/memory-paths.conf`
(the config file that LISTS memory roots, not a root itself) and NEVER the
plugin-source `memories/` tree (mem:dom/DOM_MEMORY_TREES — edited as plain
files, not a Serena store). Session Working Memory (`WM_*.md`) is exempt
everywhere in this module — same carve-out as swe_pre_edit_validate.py's
raw-memory-write guard — because the harness/daemon writes it with the Write
tool by design.

The auto-memory symlink (mem:feedback/FEEDBACK_BYPASS_AND_SETUP_LOCATION,
CLAUDE.md "Auto-Memory Symlink") redirects
`~/.claude/projects/<encoded-project>/memory` -> `<project>/.serena/memory`.
A path through that symlink does not textually match MEMORY_STORE_RE, so
is_memory_store_path() also checks os.path.realpath() of the resolved path.

Stdlib only.
"""

import os
import re
import shlex


# `.serena/memor(y|ies)` as a path SEGMENT — `(?:/|$)` after it means
# `.serena/memory-paths.conf` does NOT match (no `/` or end-of-string follows
# "memory" there; the next char is `-`). The lookbehind allows start-of-
# string, `/`, or a quote/paren/space character before `.serena` — a heredoc
# body or an inline `-c "open('.serena/memory/a.md')"` payload is quoted text,
# not a bare path, so a strict `^`/`/`-only lookbehind would miss it.
MEMORY_STORE_RE = re.compile(
    r'(?:^|[/\s"\'=(])\.serena/memor(?:y|ies)(?:/|$)')

# --- Bash command splitting (shared with swe_pre_search_docs_gate.py; that
# module imports these three names from here so BOTH modules reference the
# same regex objects — DRY, single source of truth). ------------------------
BASH_GROUP_SPLIT_RE = re.compile(r'(?:;|&&|\|\||&|\n)+')
BASH_PIPE_SPLIT_RE = re.compile(r'\|(?!\|)')
BASH_ENV_ASSIGN_RE = re.compile(
    r'^(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|\'[^\']*\'|\S*)\s+)*')

# Commands that read/scan the filesystem — when their effective cwd or any
# operand lands inside a memory store, that is raw FS access to memory.
FS_CMDS = {
    'cat', 'head', 'tail', 'less', 'more', 'grep', 'egrep', 'fgrep', 'rg',
    'ag', 'ack', 'find', 'ls', 'tree', 'awk', 'gawk', 'sed', 'wc', 'sort',
    'uniq', 'cut', 'diff', 'cmp', 'stat', 'file', 'strings', 'xxd', 'od',
    'jq', 'yq', 'nl', 'tac', 'bat', 'tee',
}

# For these commands the FIRST positional operand is typically the
# pattern/script, not a path — unless a pattern was explicitly supplied via a
# flag, in which case every remaining positional is an operand (path) and
# should be checked.
_PATTERN_FIRST_CMDS = {
    'grep', 'egrep', 'fgrep', 'rg', 'ag', 'ack', 'sed', 'awk', 'gawk',
}
_PATTERN_FLAGS = {'-e', '--regexp', '-f', '--file', '--expression'}

_INLINE_INTERPRETERS = {'python', 'python3', 'node', 'perl', 'ruby', 'php'}
_INLINE_FLAGS = {'-c', '-e', '-r'}

_REDIRECT_RE = re.compile(r'(>>?\|?)\s*(\S+)')


def _expand(path: str) -> str:
    """Expand `~`, `$HOME`, `${HOME}` in a path string (no shell execution)."""
    if not path:
        return path
    path = path.replace('${HOME}', os.path.expanduser('~'))
    path = os.path.expandvars(path) if '$HOME' in path else path
    path = os.path.expanduser(path)
    return path


def is_memory_store_path(path: str, cwd: str) -> bool:
    """True when `path` resolves inside a Serena memory store.

    Empty path -> False. `~`/$HOME/${HOME} expanded; a relative path is
    joined onto `cwd` first. A basename starting with `WM_` is exempt
    (session Working Memory — same carve-out as swe_pre_edit_validate.py's
    raw-memory-write guard). True when MEMORY_STORE_RE matches the
    normalized path OR matches os.path.realpath() of it (catches the
    auto-memory symlink `~/.claude/projects/<encoded>/memory` ->
    `<project>/.serena/memory`). Glob characters in the final path segment
    (e.g. `ref/*.md`) do not prevent a match — the regex only needs the
    `.serena/memor(y|ies)` segment earlier in the string.
    """
    if not path:
        return False
    expanded = _expand(path)
    if not os.path.isabs(expanded):
        expanded = os.path.join(cwd or os.getcwd(), expanded)
    normalized = os.path.normpath(expanded)
    if os.path.basename(normalized).startswith('WM_'):
        return False
    if MEMORY_STORE_RE.search(normalized.replace('\\', '/')):
        return True
    try:
        real = os.path.realpath(normalized)
    except OSError:
        return False
    if real != normalized and MEMORY_STORE_RE.search(real.replace('\\', '/')):
        return True
    return False


def _tokenize(stage: str) -> list:
    try:
        return shlex.split(stage)
    except ValueError:
        return stage.split()


def _strip_env_assigns(tokens: list) -> list:
    i = 0
    while i < len(tokens) and re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', tokens[i]):
        i += 1
    return tokens[i:]


def _basename_cmd(token: str) -> str:
    return os.path.basename(token or '')


def _redirect_targets(stage: str) -> list:
    """Every redirection target token in a command stage (`>`, `>>`, `>|`,
    or a bare `>path` with no space)."""
    targets = []
    for m in _REDIRECT_RE.finditer(stage):
        targets.append(m.group(2))
    return targets


def _stage_has_fs_cmd_memory_access(tokens: list, cwd_for_stage: str) -> bool:
    if not tokens:
        return False
    cmd = _basename_cmd(tokens[0])
    if cmd not in FS_CMDS:
        return False
    if is_memory_store_path(cwd_for_stage, cwd_for_stage):
        return True
    operands = tokens[1:]
    pattern_supplied_via_flag = any(t in _PATTERN_FLAGS for t in operands)
    skip_first_positional = (
        cmd in _PATTERN_FIRST_CMDS and not pattern_supplied_via_flag
    )
    seen_first_positional = False
    for tok in operands:
        if tok.startswith('-'):
            continue
        if skip_first_positional and not seen_first_positional:
            seen_first_positional = True
            continue
        if is_memory_store_path(tok, cwd_for_stage):
            return True
    return False


def _stage_has_perl_inplace_memory_access(tokens: list, cwd_for_stage: str) -> bool:
    if not tokens:
        return False
    cmd = _basename_cmd(tokens[0])
    if cmd != 'perl':
        return False
    has_inplace = any(t == '-i' or t.startswith('-i') or
                       (t == '-p' and '-i' in tokens) or
                       t.startswith('-pi') for t in tokens[1:])
    if not has_inplace:
        return False
    for tok in tokens[1:]:
        if tok.startswith('-'):
            continue
        if is_memory_store_path(tok, cwd_for_stage):
            return True
    return False


def _stage_has_inline_interpreter_memory_access(
        tokens: list, cwd_for_stage: str, whole_command: str) -> bool:
    if not tokens:
        return False
    cmd = _basename_cmd(tokens[0])
    if cmd not in _INLINE_INTERPRETERS:
        return False
    is_inline = (
        any(t in _INLINE_FLAGS for t in tokens[1:])
        or '-' in tokens[1:]
        or '<<' in whole_command
    )
    if not is_inline:
        return False
    if is_memory_store_path(cwd_for_stage, cwd_for_stage):
        return True
    return bool(MEMORY_STORE_RE.search(whole_command.replace('\\', '/')))


def bash_memory_access(command: str, cwd: str) -> bool:
    """True when `command`, run from `cwd`, performs raw filesystem access to
    a Serena memory store.

    Splits on command GROUPS (`;`, `&&`, `||`, `&`, newline) and, within each
    group, on PIPE STAGES (`|`). Tracks an effective cwd across stages/groups
    in left-to-right order: a `cd <dir>` stage updates it (`cd` alone -> home
    dir), so `cd .serena/memory && grep -rn x .` is caught via the updated
    cwd, not just the literal operand text.

    Access is detected per stage via (a) an FS_CMDS command whose effective
    cwd or an operand is a memory-store path (skipping the pattern/script
    positional for grep-family/sed/awk UNLESS a pattern was supplied via a
    flag — so `grep -rn ".serena/memory" hooks/`, searching plugin SOURCE for
    the literal string, is not flagged), (b) any redirection target that is a
    memory-store path regardless of command, (c) `perl -i`/`-pi` targeting a
    memory-store path (sed -i is covered by (a) since `sed` is in FS_CMDS),
    (d) an inline interpreter invocation (python/python3/node/perl/ruby/php
    with -c/-e/-r/a bare `-`/a heredoc) whose effective cwd is a memory store
    OR whose FULL command text contains a memory-store path (heredoc bodies
    span later lines, so the per-stage token view alone would miss them).

    NOT access: git/mkdir/ln/cp/mv/rm/touch/chmod/test/[/readlink, running a
    script FILE (`python3 scripts/x.py --root .serena/memory` — `scripts/x.py`
    is the first operand, not `-c`/`-e`/heredoc, so the inline-interpreter
    check never fires), dprint/npm.
    """
    cwd = cwd or os.getcwd()
    effective_cwd = cwd
    for group in BASH_GROUP_SPLIT_RE.split(command or ''):
        for stage in BASH_PIPE_SPLIT_RE.split(group):
            tokens = _strip_env_assigns(_tokenize(stage))
            if not tokens:
                continue
            cmd = _basename_cmd(tokens[0])

            if cmd == 'cd':
                rest = [t for t in tokens[1:] if not t.startswith('-')]
                if rest:
                    target = _expand(rest[0])
                    if not os.path.isabs(target):
                        target = os.path.join(effective_cwd, target)
                    effective_cwd = os.path.normpath(target)
                else:
                    effective_cwd = os.path.expanduser('~')
                continue

            if _stage_has_fs_cmd_memory_access(tokens, effective_cwd):
                return True
            if _stage_has_perl_inplace_memory_access(tokens, effective_cwd):
                return True
            if _stage_has_inline_interpreter_memory_access(
                    tokens, effective_cwd, command or ''):
                return True
            for target in _redirect_targets(stage):
                if is_memory_store_path(target, effective_cwd):
                    return True

    return False


_PATH_LIKE_FIELDS = ('file_path', 'notebook_path')


def tool_memory_access(tool_name: str, tool_input: dict, cwd: str) -> bool:
    """True when a single tool call would read/write a Serena memory store
    via the filesystem instead of a Serena memory MCP tool.

    Bash -> bash_memory_access(command, cwd).
    Read/Edit/Write/MultiEdit/NotebookEdit -> file_path or notebook_path.
    Grep -> `path`, and `glob` joined onto path (or cwd) if present.
    Glob -> `path`, and `pattern` joined onto path (or cwd) if present.
    Anything else -> False.
    """
    tool_input = tool_input or {}
    cwd = cwd or os.getcwd()

    if tool_name == 'Bash':
        return bash_memory_access(str(tool_input.get('command', '')), cwd)

    if tool_name in ('Read', 'Edit', 'Write', 'MultiEdit', 'NotebookEdit'):
        for field in _PATH_LIKE_FIELDS:
            val = tool_input.get(field)
            if val and is_memory_store_path(str(val), cwd):
                return True
        return False

    if tool_name == 'Grep':
        base = str(tool_input.get('path') or cwd)
        if is_memory_store_path(base, cwd):
            return True
        glob = tool_input.get('glob')
        if glob:
            joined = os.path.join(base, str(glob)) if not os.path.isabs(str(glob)) else str(glob)
            if is_memory_store_path(joined, cwd):
                return True
        return False

    if tool_name == 'Glob':
        base = str(tool_input.get('path') or cwd)
        if is_memory_store_path(base, cwd):
            return True
        pattern = tool_input.get('pattern')
        if pattern:
            pattern = str(pattern)
            joined = pattern if os.path.isabs(pattern) else os.path.join(base, pattern)
            if MEMORY_STORE_RE.search(joined.replace('\\', '/')):
                return True
            # Pattern-only forms like `**/.serena/memory/**` never join
            # meaningfully onto a non-memory base (the `**/` prefix makes it
            # an absolute-ish search root) — check the raw pattern text too.
            if MEMORY_STORE_RE.search(pattern.replace('\\', '/')):
                return True
        return False

    return False
