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

from swe_hooks.core.doc_requirements import (
    required_docs_for_path, read_obligations, memory_exists, _read_memory_text,
    _FRONTMATTER_RE, TEST_DOC_NAMES,
)

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


_TEST_DOC_NAMES_LOWER = {n.lower() for n in TEST_DOC_NAMES}


def _path_match_names(prompt: str, project_root: str, cap: int) -> list:
    """Ordered, de-duplicated memory names whose `paths:` front-matter glob
    matches a file path token named in `prompt` (edit targets) — the FULL-
    READ source. Capped at `cap`.

    Excludes TEST_DOC_NAMES (feature/FEATURE_TESTS, dev/DEV_TESTS) even when
    required_docs_for_path adds one for a test-file path — that inclusion is
    the is_test_work heuristic, not a genuine paths:-glob edit-target match,
    and belongs in the digest set (required_reading_split handles it there).
    """
    names = []
    seen = set()
    for token in prompt_paths(prompt, project_root):
        for expanded in _expand_glob_paths(token, project_root):
            for doc in required_docs_for_path(expanded, project_root):
                if doc.lower() in _TEST_DOC_NAMES_LOWER:
                    continue
                if doc.lower() not in seen:
                    seen.add(doc.lower())
                    names.append(doc)
                if len(names) >= cap:
                    return names[:cap]
    return names[:cap]


def required_reading_split(prompt: str, wm_text: str, project_root: str,
                            full_cap: int = 3, cap: int = 8):
    """Split required-reading memory names into (full_read, digest).

    Digest-first (QW1): measured that requiring a full read_memory() of
    every listed name cost subagents a median 18.7k tokens upfront (+444%
    memory cost vs pre-rollout, net -0 effectiveness: flail rate rose
    5%->8%), while 87% of listed names were read in full and never referenced
    again. Only names that match an actual edit target get a full read; the
    rest ship as an inline digest the subagent is told NOT to re-read.

    full_read: names from _path_match_names (paths:-glob matches a file path
    named in the prompt — likely edit targets), capped at `full_cap`.

    digest: everything else required_reading() used to return, in the same
    priority order: feature/FEATURE_TESTS + dev/DEV_TESTS for test work, then
    wm_memories(wm_text) (WM Memories loaded / Rules planned / Compliance
    Checklist citations). Any path-matched name beyond `full_cap` also falls
    through to digest rather than being dropped. De-duplicated against
    full_read. Combined length of both lists never exceeds `cap`.
    """
    full_read = []
    seen = set()
    for doc in _path_match_names(prompt, project_root, full_cap):
        if doc.lower() not in seen:
            seen.add(doc.lower())
            full_read.append(doc)

    digest = []

    def _add_digest(name):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            digest.append(name)

    # Path-matched names beyond full_cap still owe a digest, not silence.
    for doc in _path_match_names(prompt, project_root, cap):
        _add_digest(doc)

    if is_test_work(prompt):
        for doc in ('feature/FEATURE_TESTS', 'dev/DEV_TESTS'):
            if memory_exists(doc, project_root):
                _add_digest(doc)

    for name in wm_memories(wm_text):
        _add_digest(name)

    total_room = max(0, cap - len(full_read))
    return full_read, digest[:total_room]


def required_reading(prompt: str, wm_text: str, project_root: str, cap: int = 8) -> list:
    """The combined (full_read + digest) ordered name list — "which memories
    does this sweep touch" without the FULL-READ vs DIGEST distinction. See
    required_reading_split for the split callers that need to enforce only
    the FULL-READ subset (e.g. missing_sweep_reason's deny-avoidance set).
    """
    full_read, digest = required_reading_split(prompt, wm_text, project_root, cap=cap)
    names = list(full_read)
    seen = {n.lower() for n in names}
    for name in digest:
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names[:cap]


_BLOCK_HEADER = (
    "\n\n[swe-required-reading] FULL READ — before any other work, read "
    "these memories yourself with read_memory (the orchestrator's reads do "
    "not carry over to you):"
)

_DIGEST_HEADER = (
    "\n\nDIGEST — these are the required knowledge for this task already. Do "
    "NOT call read_memory on these unless a specific edit needs detail "
    "beyond what is summarized here:"
)


def read_description(name: str, project_root: str) -> str:
    """The memory's front-matter `description:` scalar value, or '' when the
    memory is missing, has no front-matter, or declares no `description:`.
    """
    text = _read_memory_text(name, project_root)
    if not text:
        return ''
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return ''
    desc_re = re.compile(r'^description\s*:\s*(.*)$')
    for line in m.group(1).splitlines():
        if line.startswith(' '):
            continue
        dm = desc_re.match(line.strip())
        if dm:
            return dm.group(1).strip().strip('"').strip("'")
    return ''


def required_reading_block(full_read, digest, project_root: str) -> str:
    """The `[swe-required-reading]` prompt-injection block.

    `full_read` names each get a `- read_memory("<name>")` line, followed by
    that memory's obligations (read_obligations) indented as
    `    • <obligation>` lines — omitted entirely when there are none.

    `digest` names each get a single `- <name>: <summary>` line instead,
    where <summary> is the memory's obligations joined with '; ', falling
    back to its front-matter `description:` when it declares no
    obligations, falling back to '(no digest available)' when neither is
    present. These lines ARE the required knowledge for the digest names —
    the block explicitly tells the subagent not to read_memory() them absent
    a specific need.

    Both lists empty -> "".
    """
    full_read = [n for n in (full_read or []) if n]
    digest = [n for n in (digest or []) if n]
    if not full_read and not digest:
        return ''
    lines = []
    if full_read:
        lines.append(_BLOCK_HEADER)
        for name in full_read:
            lines.append(f'- read_memory("{name}")')
            for obligation in read_obligations(name, project_root):
                lines.append(f'    • {obligation}')
    if digest:
        lines.append(_DIGEST_HEADER)
        for name in digest:
            obligations = read_obligations(name, project_root)
            if obligations:
                summary = '; '.join(obligations)
            else:
                summary = read_description(name, project_root) or '(no digest available)'
            lines.append(f'- {name}: {summary}')
    return '\n'.join(lines)
