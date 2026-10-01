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


_HEREDOC_START_RE = re.compile(r'<<-?\s*(\'?)(["\']?)(\w+)\2\1')

_DEV_NULL_LIKE = {'/dev/null', '/dev/stdout', '/dev/stderr'}
_FD_DUP_RE = re.compile(r'^\d*>&\d+$')

_SED_INPLACE_RE = re.compile(r'^-([A-Za-z]*i)(.*)$')
_PERL_INPLACE_FLAGS = ('-i', '-pi')

_COPYISH_CMDS = {'cp', 'mv', 'install'}
_TOUCH_CMDS = {'touch', 'truncate'}

# A mode string, not an arbitrary string that happens to contain w/a/x: PHP's
# fopen() modes are 1-3 chars from {r,w,a,x,+,b,t} and MUST contain at least
# one of w/a/x; Python's open() mode kwarg is similarly short. Matching the
# full quoted literal (not a substring) against that shape avoids a false
# positive like open('a.txt').read() — "a.txt" is not itself a mode string.
_MODE_STRING_RE = r'[rwaxbt+]{1,4}'

_WRITE_INDICATOR_RE = re.compile(
    r"open\(\s*[^,)]+,\s*['\"](?=[rwaxbt+]{1,4}['\"])(?=[^'\"]*[wax])" + _MODE_STRING_RE + r"['\"]"
    r"|\.write_text\(|\.write_bytes\("
    r"|writeFile\(|appendFile\("
    r"|file_put_contents\("
    r"|fopen\(\s*[^,)]+,\s*['\"](?=[rwaxbt+]{1,4}['\"])(?=[^'\"]*[wax])" + _MODE_STRING_RE + r"['\"]"
    r"|File\.write\("
    r"|shutil\.(?:copy\w*|move)\("
)

_QUOTED_STRING_RE = re.compile(r'''(["'])((?:\\.|(?!\1).)*)\1''')


def _strip_heredoc_bodies(command: str) -> str:
    """Remove heredoc BODY lines from `command` text, keeping the `<<TAG`
    introducer line intact (so its own tokens are still split as a normal
    command stage) but dropping every line up to and including the closing
    delimiter — those lines are heredoc CONTENT (e.g. a script fed to
    `python3 -`), never shell commands or write targets in their own right.

    Handles multiple heredocs in sequence (rare but possible with `&&`-joined
    commands). Delimiter may be quoted (`<<'EOF'`, `<<"EOF"`) or bare
    (`<<EOF`), and `<<-EOF` (tab-stripping form).
    """
    lines = (command or '').split('\n')
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = _HEREDOC_START_RE.search(line)
        if m:
            delim = m.group(3)
            i += 1
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            # skip the closing delimiter line itself too
            i += 1
            continue
        i += 1
    return '\n'.join(out)


def _is_dev_null_like(target: str) -> bool:
    return target in _DEV_NULL_LIKE or bool(_FD_DUP_RE.match(target))


def _stage_redirect_write_targets(stage: str) -> list:
    targets = []
    for m in _REDIRECT_RE.finditer(stage):
        target = m.group(2)
        if _is_dev_null_like(target):
            continue
        targets.append(target)
    return targets


def _flag_value(tokens: list, idx: int, flag_names: tuple) -> str:
    """Value following a `--flag VALUE` or `--flag=VALUE` token at `idx`."""
    tok = tokens[idx]
    for name in flag_names:
        if tok == name and idx + 1 < len(tokens):
            return tokens[idx + 1]
        if tok.startswith(name + '='):
            return tok[len(name) + 1:]
    return None


def _stage_tee_targets(tokens: list) -> list:
    if not tokens or _basename_cmd(tokens[0]) != 'tee':
        return []
    targets = []
    for tok in tokens[1:]:
        if tok.startswith('-'):
            continue
        targets.append(tok)
    return targets


def _stage_sed_inplace_targets(tokens: list) -> list:
    """`sed` file operands ONLY when an in-place flag is present.

    In-place forms: `-i`, `-i ''`, `-i.bak` (suffix glued on), `-i''`,
    `--in-place`, `-Ei`/`-ie`-style combined short flags ending in `i`. A
    combined flag's trailing chars after `i` (e.g. `-i.bak`) are the BSD
    suffix, consumed in place, not a following operand. A bare `-i` (no glued
    suffix) MAY be followed by a separate suffix operand on BSD (`-i ''`) —
    detected by the next token being empty-string or starting with `.`
    immediately after `-i`.
    """
    if not tokens:
        return []
    cmd = _basename_cmd(tokens[0])
    if cmd != 'sed':
        return []
    has_inplace = False
    n = len(tokens)
    i = 1
    consumed_suffix_idx = None
    while i < n:
        tok = tokens[i]
        if tok == '--in-place' or tok.startswith('--in-place='):
            has_inplace = True
            i += 1
            continue
        if tok.startswith('-') and not tok.startswith('--'):
            m = _SED_INPLACE_RE.match(tok)
            if m:
                has_inplace = True
                suffix_part = m.group(2)
                if tok == '-i' and not suffix_part:
                    # bare -i: BSD may require a following suffix arg (possibly '')
                    if i + 1 < n and (tokens[i + 1] == '' or tokens[i + 1].startswith('.')
                                       or tokens[i + 1] == "''"):
                        consumed_suffix_idx = i + 1
                i += 1
                continue
        i += 1
    if not has_inplace:
        return []
    # Determine script-expression operand(s) to exclude: -e EXPR / --expression=EXPR
    # or, absent any -e, the first bare non-flag operand is the script.
    has_e_flag = any(
        t == '-e' or t == '--expression' or t.startswith('--expression=')
        for t in tokens[1:]
    )
    targets = []
    seen_first_bare = False
    i = 1
    while i < n:
        tok = tokens[i]
        if i == consumed_suffix_idx:
            i += 1
            continue
        if tok in ('-e', '--expression'):
            i += 2  # skip flag + its value
            continue
        if tok.startswith('--expression='):
            i += 1
            continue
        if tok.startswith('-'):
            i += 1
            continue
        if not has_e_flag and not seen_first_bare:
            seen_first_bare = True
            i += 1
            continue
        targets.append(tok)
        i += 1
    return targets


def _stage_perl_inplace_targets(tokens: list) -> list:
    if not tokens or _basename_cmd(tokens[0]) != 'perl':
        return []
    has_inplace = any(
        t == '-i' or t.startswith('-i.') or t.startswith('-pi') or t == '-pi'
        for t in tokens[1:]
    )
    if not has_inplace:
        return []
    has_e_flag = any(t == '-e' or t == '-E' for t in tokens[1:])
    targets = []
    seen_first_bare = False
    skip_next = False
    for tok in tokens[1:]:
        if skip_next:
            skip_next = False
            continue
        if tok in ('-e', '-E'):
            skip_next = True
            continue
        if tok.startswith('-'):
            continue
        if not has_e_flag and not seen_first_bare:
            seen_first_bare = True
            continue
        targets.append(tok)
    return targets


def _stage_copyish_targets(tokens: list) -> list:
    """Destination operand for `cp`/`mv`/`install` — last non-flag operand,
    or the `-t DIR` operand when given (then EVERY remaining source becomes
    a target inside that dir — but since paths are returned unresolved as
    written, we only report the `-t` directory itself, matching "the file
    paths ... as written in the command")."""
    if not tokens:
        return []
    cmd = _basename_cmd(tokens[0])
    if cmd not in _COPYISH_CMDS:
        return []
    operands = []
    i = 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok in ('-t', '--target-directory'):
            if i + 1 < n:
                return [tokens[i + 1]]
            return []
        if tok.startswith('--target-directory='):
            return [tok[len('--target-directory='):]]
        if tok.startswith('-'):
            i += 1
            continue
        operands.append(tok)
        i += 1
    if len(operands) >= 2:
        return [operands[-1]]
    return []


_TRUNCATE_VALUE_FLAGS = ('-s', '--size', '-o', '--io-blocks')


def _stage_touch_targets(tokens: list) -> list:
    if not tokens:
        return []
    cmd = _basename_cmd(tokens[0])
    if cmd not in _TOUCH_CMDS:
        return []
    targets = []
    i = 1
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if cmd == 'truncate' and tok in _TRUNCATE_VALUE_FLAGS:
            i += 2  # skip flag + its value (e.g. `-s 0`)
            continue
        if cmd == 'truncate' and any(
                tok.startswith(f + '=') for f in _TRUNCATE_VALUE_FLAGS):
            i += 1
            continue
        if tok.startswith('-'):
            i += 1
            continue
        targets.append(tok)
        i += 1
    return targets


def _stage_dd_targets(tokens: list) -> list:
    if not tokens or _basename_cmd(tokens[0]) != 'dd':
        return []
    targets = []
    for tok in tokens[1:]:
        if tok.startswith('of='):
            targets.append(tok[len('of='):])
    return targets


def _looks_like_path_literal(text: str) -> bool:
    if '/' in text:
        return True
    _, ext = os.path.splitext(text)
    return bool(ext) and len(ext) <= 8 and ext[1:].isalnum()


def _inline_code_write_targets(code: str) -> list:
    """Quoted string literals in `code` that look like file paths, ONLY when
    `code` also contains a write indicator (open(...'w'/'a'/'x'...),
    write_text/write_bytes, writeFile/appendFile, file_put_contents,
    fopen(...'w'/'a'/'x'...), File.write, shutil.copy*/move). Returns []
    otherwise (read-only inline code reports no write targets)."""
    if not _WRITE_INDICATOR_RE.search(code):
        return []
    targets = []
    for m in _QUOTED_STRING_RE.finditer(code):
        literal = m.group(2)
        if _looks_like_path_literal(literal):
            targets.append(literal)
    return targets


def _stage_inline_interpreter_write_targets(
        tokens: list, whole_command: str, stage: str) -> list:
    if not tokens:
        return []
    cmd = _basename_cmd(tokens[0])
    if cmd not in _INLINE_INTERPRETERS:
        return []
    code_parts = []
    i = 1
    n = len(tokens)
    fed_heredoc_or_dash = '-' in tokens[1:] or '<<' in stage
    while i < n:
        tok = tokens[i]
        if tok in _INLINE_FLAGS and i + 1 < n:
            code_parts.append(tokens[i + 1])
            i += 2
            continue
        i += 1
    if not code_parts and fed_heredoc_or_dash:
        # Heredoc body: pull the raw text between the `<<TAG` introducer and
        # the closing delimiter out of the ORIGINAL (non-stripped) command.
        m = _HEREDOC_START_RE.search(whole_command)
        if m:
            delim = m.group(3)
            after = whole_command[m.end():]
            lines = after.split('\n')
            body_lines = []
            for line in lines[1:] if after.startswith('\n') else lines:
                if line.strip() == delim:
                    break
                body_lines.append(line)
            code_parts.append('\n'.join(body_lines))
    code = '\n'.join(code_parts)
    if not code:
        return []
    return _inline_code_write_targets(code)


def _stage_shell_c_recursion_targets(tokens: list) -> list:
    if not tokens:
        return []
    cmd = _basename_cmd(tokens[0])
    if cmd not in ('bash', 'sh', 'zsh'):
        return []
    for idx, tok in enumerate(tokens[1:], start=1):
        if tok == '-c' and idx + 1 < len(tokens):
            return bash_write_targets(tokens[idx + 1])
    return []


def _mask_quoted_spans(text: str) -> tuple:
    """Replace the CONTENTS of every top-level quoted span in `text` with a
    placeholder of the same length containing no shell metacharacters, so
    `BASH_GROUP_SPLIT_RE`/`BASH_PIPE_SPLIT_RE` (naive, non-shell-aware regex
    splits) never slice a group/pipe boundary out of literal text sitting
    inside a `-c '...'`/`-e "..."`/heredoc-fed quoted argument (e.g. `python3
    -c "import shutil; shutil.copy(...)"` must stay ONE token stream, not be
    cut at the `;` inside the quotes).

    Returns (masked_text, originals) where `originals` is a list of the
    original span texts (WITH their surrounding quote characters) in order —
    masked_text has each span replaced by `\\x00<index>\\x00` of fixed shape
    so it round-trips through tokenizing unchanged in length-insensitive
    code, then `_unmask` swaps the placeholders back for the real text before
    the code/expression text is inspected.
    """
    originals = []

    def _replace(m):
        originals.append(m.group(0))
        return '\x00%d\x00' % (len(originals) - 1)

    masked = _QUOTED_STRING_RE.sub(_replace, text)
    return masked, originals


def _unmask(text: str, originals: list) -> str:
    def _restore(m):
        return originals[int(m.group(1))]

    return re.sub(r'\x00(\d+)\x00', _restore, text)


def bash_write_targets(command: str) -> list:
    """File paths `command` WRITES, as written (unresolved paths, de-duplicated,
    in order of first appearance).

    Splits on command GROUPS (`;`, `&&`, `||`, `&`, newline) then PIPE STAGES
    (`|`) — same tokenizer/splitters as bash_memory_access — after first
    stripping heredoc BODY lines (a heredoc body is content, not commands, so
    `cat > f <<'EOF'\\n> x\\nEOF` must report only `f`, never a redirect
    parsed out of the body text).

    Detected per stage:
      - redirection targets `>`, `>>`, `>|`, `&>`, `N>` (fd dups like `2>&1`
        and /dev/null|/dev/stdout|/dev/stderr excluded);
      - `tee` (and `tee -a`) file operands;
      - `sed` file operands ONLY with an in-place flag (`-i`, `-i ''`,
        `-i.bak`, `--in-place`, combined `-Ei`) — the script expression
        (`-e EXPR` or the first bare operand) is excluded;
      - `perl` file operands with `-i`/`-pi`/`-i.bak` (script expression via
        `-e`/first bare operand excluded same as sed);
      - `cp`/`mv`/`install` destination (last non-flag operand, or the `-t
        DIR` operand);
      - `touch`/`truncate` file operands; `dd of=PATH`;
      - inline interpreters (python/python3/node/php/ruby/perl, invoked with
        `-c`/`-e`/`-r`, fed `-`, or fed a heredoc) — quoted string literals
        that look like paths (contain `/` or end in a short file extension),
        ONLY when the code also contains a write indicator (open(...'w'/'a'/
        'x'...), write_text/write_bytes, writeFile/appendFile,
        file_put_contents, fopen(...'w'/'a'/'x'...), File.write,
        shutil.copy*/move) — otherwise none;
      - `bash -c '...'`/`sh -c '...'`/`zsh -c '...'` — recurses into the
        quoted command string, merging its own write targets in.

    NOT included: `git`, `mkdir`, `rm`, `ln` (ownership/existence operations,
    never a content write this function is meant to flag).

    KNOWN LIMITATION: the shared `BASH_PIPE_SPLIT_RE` (`\\|(?!\\|)`, reused
    unchanged from bash_memory_access) has no special case for the `>|`
    clobber redirect's bare `|` character — `echo x >| a.txt` is split into
    pipe stages at that `|`, so the target is not detected (same gap exists
    in bash_memory_access for a memory-store path after `>|`).
    """
    stripped = _strip_heredoc_bodies(command or '')
    # Mask quoted-span CONTENTS before group/pipe splitting: the split
    # regexes are naive text regexes, not shell-aware, so a `;`/`&&`/`|`
    # appearing inside a `-c '...'`/`-e "..."` quoted argument (e.g. `python3
    # -c "import shutil; shutil.copy(...)"`) would otherwise be sliced into
    # two separate "stages", corrupting the inline-interpreter code text.
    masked, originals = _mask_quoted_spans(stripped)

    seen = []
    seen_set = set()

    def _add(target):
        if target and target not in seen_set:
            seen_set.add(target)
            seen.append(target)

    for group in BASH_GROUP_SPLIT_RE.split(masked):
        for masked_stage in BASH_PIPE_SPLIT_RE.split(group):
            stage = _unmask(masked_stage, originals)
            tokens = _strip_env_assigns(_tokenize(stage))
            if not tokens:
                continue
            cmd = _basename_cmd(tokens[0])
            if cmd in ('git', 'mkdir', 'rm', 'ln'):
                continue

            # A `bash -c '...'`/`sh -c '...'`/`zsh -c '...'` stage is
            # recursed into exclusively — the literal stage text (e.g. the
            # quoted `-c` argument split by shlex) must NOT also be scanned
            # by the other per-stage detectors, or a redirect/write inside
            # the quoted string gets counted twice (once raw, once via the
            # recursive parse of the clean sub-command).
            shell_c_targets = _stage_shell_c_recursion_targets(tokens)
            if shell_c_targets:
                for target in shell_c_targets:
                    _add(target)
                continue

            # Redirect detection runs on the MASKED stage text — a `>`
            # appearing inside a quoted argument (e.g. sed's own script
            # `'s/>/x/'`) is not a real shell redirect, and the regex-based
            # `_stage_redirect_write_targets` has no quote-awareness of its
            # own, unlike the shlex-tokenized detectors above.
            for target in _stage_redirect_write_targets(masked_stage):
                _add(target)
            for target in _stage_tee_targets(tokens):
                _add(target)
            for target in _stage_sed_inplace_targets(tokens):
                _add(target)
            for target in _stage_perl_inplace_targets(tokens):
                _add(target)
            for target in _stage_copyish_targets(tokens):
                _add(target)
            for target in _stage_touch_targets(tokens):
                _add(target)
            for target in _stage_dd_targets(tokens):
                _add(target)
            for target in _stage_inline_interpreter_write_targets(
                    tokens, command or '', stage):
                _add(target)

    return seen


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
