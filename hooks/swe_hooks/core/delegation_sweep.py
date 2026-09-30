"""Per-subagent doc-sweep computation — what a delegated Agent/Task prompt
must carry so the spawned subagent starts with the orchestrator's own doc
sweep, instead of re-discovering (or skipping) it.

Pure stdlib. wm_memories/prompt_paths/is_test_work/required_reading are pure
functions over already-read text; required_reading_block additionally reads
memory front-matter via doc_requirements.read_obligations (project_root I/O
only, no network/subprocess). No gate logic lives here — this module only
computes WHAT a subagent should read; hooks/pre/swe_pre_agent_model_gate.py
decides whether to deny a call for the mismatch (see missing_sweep_reason
there) and appends the block this module builds.
"""

import glob as _glob
import os
import re

from swe_hooks.core.doc_requirements import required_docs_for_path, read_obligations, memory_exists

# Prefixes/names excluded from a WM-sourced required-reading list: workflow
# machinery (wf/*, claude/*), session state (WM_*), and the four sweep-
# excluded topics (spec/report/research/project — see
# ref/REF_WF_CLASSIFY_SWEEP "Sweep Exclusions": never bulk-loaded/demanded).
_EXCLUDED_PREFIXES = ('wf/', 'claude/', 'wm_', 'spec/', 'report/', 'research/', 'project/')

_MEMORIES_LOADED_RE = re.compile(
    r'\*\*Memories loaded\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)
_RULES_PLANNED_RE = re.compile(
    r'\*\*Rules planned\*\*:?[ \t]*(.*)$', re.IGNORECASE | re.MULTILINE)
_COMPLIANCE_CHECKLIST_RE = re.compile(
    r'^#+\s*Compliance Checklist\s*\n(.*?)(?=\n#+\s|\Z)',
    re.IGNORECASE | re.MULTILINE | re.DOTALL)
_MEM_CITATION_RE = re.compile(r'\(mem:([A-Za-z0-9_/.-]+)\)')

_TEST_WORK_RE = re.compile(
    r'\btests?\b|\bunittest\b|\bpytest\b|\bspec\b|tests/', re.IGNORECASE)

# Source-file extensions a bare (no-slash) token may still name a path via.
_SOURCE_EXTENSIONS = (
    '.py', '.js', '.jsx', '.ts', '.tsx', '.php', '.json', '.md', '.sh',
    '.yml', '.yaml', '.feature', '.rb', '.go', '.java', '.css', '.html',
)

_STRIP_CHARS = '`\'",;:!()[]{}<>'


def _clean_token(tok: str) -> str:
    """Strip quoting/bracket punctuation, then a trailing sentence-period —
    but ONLY when what remains still looks path-like (contains '/', or ends
    in a known source extension). This lets 'file.py.' and 'config.json.' at
    a sentence end correctly lose the trailing '.', while 'hooks/post/*.'
    loses the trailing '.' but KEEPS the glob '*' — '*'/'?' are legitimate
    glob metacharacters _expand_glob_paths needs intact, and stripping them
    unconditionally would turn a glob token into a literal, non-matching
    directory path."""
    tok = tok.strip(_STRIP_CHARS)
    while tok.endswith('.'):
        candidate = tok[:-1]
        if '/' in candidate or any(
                candidate.lower().endswith(ext) for ext in _SOURCE_EXTENSIONS):
            tok = candidate
        else:
            break
    return tok


def _strip_annotation(name: str) -> str:
    """Drop a trailing ' - note' / ' (note)' / em-dash annotation from a
    comma-split memory-name token, and any surrounding backticks."""
    name = name.strip().strip('`').strip()
    # Cut at the first annotation separator.
    for sep in (' — ', ' – ', ' - ', '(', '['):
        idx = name.find(sep)
        if idx > 0:
            name = name[:idx].strip()
    return name.strip('`').strip()


def _is_excluded_name(name: str) -> bool:
    lname = name.lower()
    for prefix in _EXCLUDED_PREFIXES:
        if lname.startswith(prefix):
            return True
    return False


def wm_memories(wm_text: str) -> list:
    """Memory names cited in the orchestrator's WM as already-loaded or
    already-planned context: `**Memories loaded**:` / `**Rules planned**:`
    line values (comma-separated, annotations/backticks stripped), plus
    every `(mem:NAME)` citation inside a `## Compliance Checklist` section.

    Excludes wf/*, claude/*, WM_*, and the sweep-excluded topics
    (spec/report/research/project). Order: loaded, then planned, then
    checklist citations; de-duplicated, first occurrence wins.
    """
    text = str(wm_text or '')
    names = []
    seen = set()

    def _add(name):
        name = name.strip()
        if not name or name.lower() in seen or _is_excluded_name(name):
            return
        seen.add(name.lower())
        names.append(name)

    for line_tail in _MEMORIES_LOADED_RE.findall(text):
        for token in line_tail.split(','):
            cleaned = _strip_annotation(token)
            if cleaned and cleaned.lower() != 'no-feature':
                _add(cleaned)

    for line_tail in _RULES_PLANNED_RE.findall(text):
        for token in line_tail.split(','):
            cleaned = _strip_annotation(token)
            if cleaned:
                _add(cleaned)

    checklist_m = _COMPLIANCE_CHECKLIST_RE.search(text)
    if checklist_m:
        for cited in _MEM_CITATION_RE.findall(checklist_m.group(1)):
            _add(cited.strip())

    return names


def _looks_like_path(token: str) -> bool:
    if '/' in token:
        return True
    lower = token.lower()
    return any(lower.endswith(ext) for ext in _SOURCE_EXTENSIONS)


def prompt_paths(prompt: str, project_root: str) -> list:
    """Repo-relative file-path tokens mentioned in `prompt`.

    A token qualifies when it contains '/' or ends in a known source
    extension. Backticks/quotes and trailing punctuation are stripped. An
    absolute path under project_root is relativized; one outside
    project_root (or an absolute path when project_root is falsy) is kept
    as-is (best effort — required_reading's glob/path matching simply won't
    hit anything for it). A glob token (e.g. 'hooks/post/*') is kept
    verbatim — required_reading expands it separately.

    Order preserved, de-duplicated (first occurrence wins).
    """
    text = str(prompt or '')
    project_root = project_root or ''
    out = []
    seen = set()
    for raw in re.split(r'[\s,;]+', text):
        token = _clean_token(raw)
        if not token or not _looks_like_path(token):
            continue
        # Discard obvious non-path noise: bare URLs, tags like [swe-budget: 5].
        if '://' in token or token.startswith('[') or token.startswith('http'):
            continue
        candidate = token
        if os.path.isabs(candidate) and project_root:
            try:
                rel = os.path.relpath(candidate, project_root)
            except ValueError:
                rel = candidate
            if not rel.startswith('..'):
                candidate = rel
        candidate = candidate.replace('\\', '/')
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def is_test_work(prompt: str) -> bool:
    """True when `prompt` mentions test/tests/unittest/pytest/spec/tests/."""
    return bool(_TEST_WORK_RE.search(str(prompt or '')))


def _expand_glob_paths(token: str, project_root: str) -> list:
    """Expand a glob-looking path token (contains '*' or '?') against
    project_root, returning repo-relative matches. A non-glob token is
    returned as a single-element list unchanged. No matches -> []."""
    if '*' not in token and '?' not in token:
        return [token]
    pattern = os.path.join(project_root or '.', token)
    matches = _glob.glob(pattern)
    rel = []
    for m in matches:
        try:
            rel.append(os.path.relpath(m, project_root or '.').replace('\\', '/'))
        except ValueError:
            continue
    return rel


def required_reading(prompt: str, wm_text: str, project_root: str, cap: int = 8) -> list:
    """Ordered, de-duplicated required-reading memory names for a subagent
    prompt, capped at `cap` entries.

    Sources, in priority order:
      1. required_docs_for_path for every path token in `prompt` (glob
         tokens expanded via glob.glob under project_root first).
      2. feature/FEATURE_TESTS + dev/DEV_TESTS when is_test_work(prompt) and
         they exist under project_root.
      3. wm_memories(wm_text) — the orchestrator's own loaded/planned/cited
         memories.
    """
    names = []
    seen = set()

    def _add(name):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)

    for token in prompt_paths(prompt, project_root):
        for expanded in _expand_glob_paths(token, project_root):
            for doc in required_docs_for_path(expanded, project_root):
                _add(doc)
                if len(names) >= cap:
                    return names[:cap]

    if is_test_work(prompt):
        for doc in ('feature/FEATURE_TESTS', 'dev/DEV_TESTS'):
            if memory_exists(doc, project_root):
                _add(doc)
                if len(names) >= cap:
                    return names[:cap]

    for name in wm_memories(wm_text):
        _add(name)
        if len(names) >= cap:
            return names[:cap]

    return names[:cap]


_BLOCK_HEADER = (
    "\n\n[swe-required-reading] Before any other work, read these memories "
    "yourself with read_memory — the orchestrator's reads do not carry over "
    "to you:"
)


def required_reading_block(names, project_root: str) -> str:
    """The `[swe-required-reading]` prompt-injection block for `names`.

    Empty `names` -> "". Each name gets a `- read_memory("<name>")` line,
    followed by its obligations (read_obligations) indented as
    `    • <obligation>` lines — omitted entirely when there are none.
    """
    names = [n for n in (names or []) if n]
    if not names:
        return ''
    lines = [_BLOCK_HEADER]
    for name in names:
        lines.append(f'- read_memory("{name}")')
        for obligation in read_obligations(name, project_root):
            lines.append(f'    • {obligation}')
    return '\n'.join(lines)
