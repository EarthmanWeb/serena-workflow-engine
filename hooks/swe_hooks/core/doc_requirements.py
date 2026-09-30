"""Path -> required-memory API (stage 1 of per-subagent doc enforcement).

Maps a file being edited to the memories that DOCUMENT it — feature/*.md and
dev/*.md files whose YAML front-matter `paths:` (or `metadata.paths:`) glob
list matches the file — plus the project's test-harness memories
(feature/FEATURE_TESTS, dev/DEV_TESTS) when the target is a test artifact.

Stage 2 wires this into a gate; this module is the pure, testable API only.
Stdlib only, no PyYAML dependency — front-matter is parsed by hand (see
parse_paths_frontmatter).
"""

import fnmatch
import os
import re

from swe_hooks.core.memory_size import parse_root_arg

# Test-artifact detection. COPIED from hooks/pre/swe_pre_edit_validate.py
# (TEST_TARGET_RE, lines ~62-69) rather than imported, to avoid coupling this
# new module's import graph to a PreToolUse hook script in this stage. Stage 2
# makes swe_pre_edit_validate import ITS copy from here instead, so the regex
# has exactly one source of truth going forward.
TEST_TARGET_RE = re.compile(
    r'(^|/)tests?/'
    r'|(^|/)e2e/'
    r'|(^|/)test_[^/]+\.py$'
    r'|\.(test|spec)\.[jt]sx?$'
    r'|\.spec\.ts$'
    r'|\.feature$'
    r'|Test\.php$'
)

# Test-harness memories, filtered by existence (memory_exists) before being
# added to a required-docs list.
TEST_DOC_NAMES = ('feature/FEATURE_TESTS', 'dev/DEV_TESTS')

# Memory subdirectories scanned for paths: front-matter.
_SCANNED_TOPICS = ('feature', 'dev')

# Per-process cache of the scanned (name, globs) index, keyed by project_root.
_INDEX_CACHE = {}


def is_test_target(file_path: str) -> bool:
    """True when file_path is a test artifact (see TEST_TARGET_RE)."""
    return bool(TEST_TARGET_RE.search(str(file_path or '').replace('\\', '/')))


def memory_roots(project_root: str) -> list:
    """Memory root directories for `project_root`.

    Reads .serena/memory-paths.conf using memory_size.parse_root_arg for the
    per-line `[alias=]path[:ro]` grammar (single source of truth for that
    syntax), but resolves a relative path against project_root — NOT
    memory_size.load_conf_roots' own getcwd()-relative resolution, which
    breaks whenever project_root != the calling process's cwd (a hook
    process's cwd cannot be relied on to be the project root; see
    core.session.get_project_root's whole reason for existing). Falls back
    to [project_root/.serena/memory] when the conf is absent or resolves no
    roots.

    An aliased root (`alias=path` in the conf) is returned as-is; callers
    that need the alias prefix for memory names use it alongside the
    directory (see _build_index).
    """
    conf_path = os.path.join(project_root, '.serena', 'memory-paths.conf')
    roots = []
    if os.path.isfile(conf_path):
        try:
            with open(conf_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except OSError:
            lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.endswith(':ro'):
                line = line[:-len(':ro')].strip()
            if not line:
                continue
            alias, path = parse_root_arg(line)
            if not os.path.isabs(path):
                path = os.path.join(project_root, path)
            roots.append((alias, os.path.normpath(path)))
    if not roots:
        roots = [(None, os.path.join(project_root, '.serena', 'memory'))]
    return roots


def _name_for(alias, rel_name: str) -> str:
    """Memory name with alias prefix applied when aliased."""
    return f'{alias}/{rel_name}' if alias else rel_name


def memory_exists(name: str, project_root: str) -> bool:
    """True when memory `name` (e.g. 'feature/FEATURE_TESTS' or
    'alias/feature/X') exists as a .md file under one of project_root's
    memory roots."""
    roots = memory_roots(project_root)
    for alias, root_dir in roots:
        rel = name
        if alias:
            prefix = f'{alias}/'
            if not name.startswith(prefix):
                continue
            rel = name[len(prefix):]
        candidate = os.path.join(root_dir, rel + '.md')
        if os.path.isfile(candidate):
            return True
    return False


_FRONTMATTER_RE = re.compile(r'\A---\s*\n(.*?\n)---\s*\n?', re.DOTALL)


def parse_paths_frontmatter(text: str) -> list:
    """Extract a `paths:` (or `metadata.paths:`) glob list from a memory's
    leading YAML front-matter block, WITHOUT a yaml dependency.

    Accepts:
      paths:
        - "feature/**/*.py"
        - foo/*.md
      paths: ["a/*.py", "b/*.md"]
      metadata:
        paths:
          - x/*.py

    A top-level `paths:` and a nested `metadata.paths:` are both honored
    (their globs are combined). Returns [] when there is no front-matter, or
    no paths key, or the file has no leading '---' block.
    """
    if not text:
        return []
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return []
    fm_lines = m.group(1).splitlines()

    globs = []
    globs.extend(_extract_key_list(fm_lines, 'paths', top_level=True))
    globs.extend(_extract_nested_key_list(fm_lines, 'metadata', 'paths'))
    return globs


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def _parse_inline_list(raw: str) -> list:
    """Parse a `[a, b, "c"]` inline YAML flow list into plain strings."""
    raw = raw.strip()
    if raw.startswith('[') and raw.endswith(']'):
        raw = raw[1:-1]
    items = []
    for part in raw.split(','):
        part = part.strip().strip('"').strip("'")
        if part:
            items.append(part)
    return items


def _extract_key_list(lines, key: str, top_level: bool = False) -> list:
    """Find a top-level `key:` entry in `lines` and return its list values,
    whether block-style (`- item` on following more-indented lines) or an
    inline flow list on the same line."""
    key_re = re.compile(rf'^{re.escape(key)}\s*:\s*(.*)$')
    for i, line in enumerate(lines):
        if _indent_of(line) != 0:
            continue
        stripped = line.strip()
        m = key_re.match(stripped)
        if not m:
            continue
        inline = m.group(1).strip()
        if inline:
            return _parse_inline_list(inline)
        # Block list: following lines more-indented, starting with '- '.
        items = []
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            if _indent_of(nxt) == 0:
                break
            item = nxt.strip()
            if item.startswith('- '):
                item = item[2:].strip().strip('"').strip("'")
                if item:
                    items.append(item)
            else:
                break
        return items
    return []


def _extract_nested_key_list(lines, parent_key: str, child_key: str) -> list:
    """Find `parent_key:` at top level, then `child_key:` nested one level
    under it, and return its list values (block or inline)."""
    parent_re = re.compile(rf'^{re.escape(parent_key)}\s*:\s*$')
    for i, line in enumerate(lines):
        if _indent_of(line) != 0:
            continue
        if not parent_re.match(line.strip()):
            continue
        # Collect the parent's indented block.
        block = []
        parent_child_indent = None
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            indent = _indent_of(nxt)
            if indent == 0:
                break
            if parent_child_indent is None:
                parent_child_indent = indent
            if indent != parent_child_indent:
                # Deeper indent belongs to the last collected key's value;
                # keep it in block so _extract_key_list can see it.
                block.append(nxt)
                continue
            block.append(nxt)
        # Re-run the flat-list extractor against the dedented block, matching
        # child_key at the parent's child indent level.
        child_re = re.compile(rf'^{re.escape(child_key)}\s*:\s*(.*)$')
        for k, bline in enumerate(block):
            if _indent_of(bline) != parent_child_indent:
                continue
            m = child_re.match(bline.strip())
            if not m:
                continue
            inline = m.group(1).strip()
            if inline:
                return _parse_inline_list(inline)
            items = []
            for bl in block[k + 1:]:
                if not bl.strip():
                    continue
                if _indent_of(bl) <= parent_child_indent:
                    break
                item = bl.strip()
                if item.startswith('- '):
                    item = item[2:].strip().strip('"').strip("'")
                    if item:
                        items.append(item)
                else:
                    break
            return items
        return []
    return []


def _glob_to_regex(glob_pat: str):
    """Compile a glob pattern to a regex, with '**/' matching zero or more
    path segments and '*' matching within one segment (never crossing '/')."""
    pat = glob_pat.replace('\\', '/')
    out = []
    i = 0
    n = len(pat)
    while i < n:
        if pat[i:i + 3] == '**/':
            out.append('(?:.*/)?')
            i += 3
        elif pat[i:i + 2] == '**':
            out.append('.*')
            i += 2
        elif pat[i] == '*':
            out.append('[^/]*')
            i += 1
        elif pat[i] == '?':
            out.append('[^/]')
            i += 1
        else:
            out.append(re.escape(pat[i]))
            i += 1
    return re.compile('^' + ''.join(out) + '$')


def _glob_matches(glob_pat: str, rel_path: str) -> bool:
    rel_path = rel_path.replace('\\', '/')
    try:
        return bool(_glob_to_regex(glob_pat).match(rel_path))
    except re.error:
        return fnmatch.fnmatch(rel_path, glob_pat)


def _build_index(project_root: str):
    """Scan feature/*.md and dev/*.md under every memory root; return a list
    of (memory_name, globs) tuples. Cached per project_root."""
    if project_root in _INDEX_CACHE:
        return _INDEX_CACHE[project_root]

    index = []
    for alias, root_dir in memory_roots(project_root):
        for topic in _SCANNED_TOPICS:
            topic_dir = os.path.join(root_dir, topic)
            if not os.path.isdir(topic_dir):
                continue
            try:
                entries = sorted(os.listdir(topic_dir))
            except OSError:
                continue
            for fname in entries:
                if not fname.endswith('.md'):
                    continue
                fpath = os.path.join(topic_dir, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8') as f:
                        text = f.read()
                except (IOError, OSError):
                    continue
                globs = parse_paths_frontmatter(text)
                if not globs:
                    continue
                rel_name = f'{topic}/{fname[:-3]}'
                name = _name_for(alias, rel_name)
                index.append((name, globs))

    _INDEX_CACHE[project_root] = index
    return index


def required_docs_for_path(file_path: str, project_root: str) -> list:
    """Memories required for editing `file_path`, sorted and de-duplicated.

    file_path is made relative to project_root before glob matching (an
    already-relative path is used as-is). A feature/dev memory is required
    when ANY of its `paths:` globs matches. When file_path is a test
    artifact (is_test_target), 'feature/FEATURE_TESTS' and 'dev/DEV_TESTS'
    are added too, filtered by memory_exists (never demand a doc the project
    does not have).
    """
    project_root = os.path.abspath(project_root)
    abs_path = file_path
    if not os.path.isabs(abs_path):
        abs_path = os.path.join(project_root, file_path)
    try:
        rel_path = os.path.relpath(abs_path, project_root)
    except ValueError:
        rel_path = file_path
    rel_path = rel_path.replace('\\', '/')

    required = set()
    for name, globs in _build_index(project_root):
        for g in globs:
            if _glob_matches(g, rel_path):
                required.add(name)
                break

    if is_test_target(rel_path):
        for name in TEST_DOC_NAMES:
            if memory_exists(name, project_root):
                required.add(name)

    return sorted(required)


def unread_required_docs(file_path: str, project_root: str, read_names) -> list:
    """required_docs_for_path(...) filtered to names NOT in `read_names`.

    Comparison uses stream.normalize_memory_name when available (so a
    'mem:'-prefixed or '.md'-suffixed read_names entry still matches) and
    falls back to a plain lowercase compare if core.stream cannot be
    imported (keeps this module usable standalone).
    """
    try:
        from swe_hooks.core.stream import normalize_memory_name
    except ImportError:
        def normalize_memory_name(n):
            return str(n).strip().lower()

    normalized_read = {normalize_memory_name(str(n)) for n in (read_names or [])}
    required = required_docs_for_path(file_path, project_root)
    return [n for n in required if normalize_memory_name(n) not in normalized_read]
