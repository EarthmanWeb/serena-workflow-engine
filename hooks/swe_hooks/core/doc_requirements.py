"""Path -> required-memory API (stage 1 of per-subagent doc enforcement).

Maps a file being edited to the memories that DOCUMENT it — feature/*.md and
dev/*.md files whose YAML front-matter `paths:` (or `metadata.paths:`) glob
list matches the file — plus the project's test-harness memories
(feature/FEATURE_TESTS, dev/DEV_TESTS) when the target is a test artifact.

Two additional behaviors on top of the pure paths:-glob index:

1. Extension-based dev-standards FALLBACK (`fallback_dev_docs` /
   `EXTENSION_LANGUAGE_FALLBACK`): when NO paths:-matched memory for a file
   is a `dev/*` name (i.e. the project's dev-standards memories either don't
   exist or have no `paths:` front-matter covering this file), and the
   file's suffix is a known language extension, the fallback adds every
   `dev/DEV_<LANGUAGE>` memory (in priority order for that extension) that
   actually exists, plus `feature/FEATURE_DEV_STANDARDS` if it exists. This
   prevents the edit doc-gate from silently never firing for a dev-standards
   memory that forgot (or never had) a `paths:` block.
2. The plugin-SHIPPED `memories/` root's `paths:` globs (e.g. FEATURE_SWE's
   `hooks/**`) are scoped to the plugin SOURCE repo only (see `_build_index`)
   — they must not demand FEATURE_SWE in an unrelated project that merely
   happens to have a `hooks/` directory.

Stage 2 wires this into a gate; this module is the pure, testable API only.
Stdlib only, no PyYAML dependency — front-matter is parsed by hand (see
parse_paths_frontmatter).
"""

import fnmatch
import json
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

# Extension -> ordered candidate dev/DEV_<KEY> language keys, longest suffix
# matched first (see EXTENSION_LANGUAGE_FALLBACK lookup order in
# fallback_dev_docs). Order within a tuple is priority (most to least
# specific language first) — every candidate that memory_exists is added,
# not just the first match.
EXTENSION_LANGUAGE_FALLBACK = (
    ('.blade.php', ('BLADEONE', 'BLADE', 'PHP')),
    ('.php', ('PHP',)),
    ('.jsx', ('JAVASCRIPT', 'JS')),
    ('.mjs', ('JAVASCRIPT', 'JS')),
    ('.cjs', ('JAVASCRIPT', 'JS')),
    ('.js', ('JAVASCRIPT', 'JS')),
    ('.tsx', ('TYPESCRIPT', 'JAVASCRIPT')),
    ('.ts', ('TYPESCRIPT', 'JAVASCRIPT')),
    ('.scss', ('SCSS', 'SASS', 'CSS')),
    ('.sass', ('SCSS', 'SASS', 'CSS')),
    ('.css', ('CSS', 'SCSS')),
    ('.py', ('PYTHON',)),
    ('.rb', ('RUBY',)),
    ('.go', ('GO',)),
    ('.rs', ('RUST',)),
    ('.java', ('JAVA',)),
    ('.sh', ('BASH', 'SHELL')),
    ('.bash', ('BASH', 'SHELL')),
    ('.twig', ('TWIG',)),
    ('.vue', ('VUE', 'JAVASCRIPT')),
)
# Sorted longest-suffix-first so '.blade.php' is checked before '.php'.
_EXTENSION_LANGUAGE_FALLBACK_SORTED = tuple(
    sorted(EXTENSION_LANGUAGE_FALLBACK, key=lambda pair: -len(pair[0])))


def is_test_target(file_path: str) -> bool:
    """True when file_path is a test artifact (see TEST_TARGET_RE)."""
    return bool(TEST_TARGET_RE.search(str(file_path or '').replace('\\', '/')))


def _shipped_memories_root() -> str:
    """The plugin's shipped `memories/` directory — read-only, ships with the
    plugin (see FEATURE_SWE "Source Location"): `<repo>/memories/`.

    Resolution order:
      1. `CLAUDE_PLUGIN_ROOT` env var (set by the harness for an installed
         plugin, and by tests/_hookutil.py for a dev checkout) — join
         'memories'.
      2. This module's own location: hooks/swe_hooks/core/doc_requirements.py
         -> `<hooks>/../memories` (i.e. `<repo>/memories` in this source
         checkout, since `<hooks>` = `hooks/`).
    Neither branch checks existence — callers (memory_roots) filter that.
    """
    plugin_root = os.environ.get('CLAUDE_PLUGIN_ROOT', '').strip()
    if plugin_root:
        return os.path.normpath(os.path.join(plugin_root, 'memories'))
    hooks_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.normpath(os.path.join(hooks_dir, '..', 'memories'))


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

    ALSO always appends the plugin's shipped `memories/` root (see
    _shipped_memories_root), UNALIASED, at LOWEST precedence (last in the
    list) — the shipped FEATURE_*/DEV_* memories (e.g. feature/FEATURE_SWE)
    carry `paths:` front-matter too and must be visible to path matching,
    not just the conf-configured project roots. De-duplicated when it
    normalizes to the same directory as a conf root (own-repo dev checkout,
    where memory-paths.conf may already point at `memories/`).
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

    shipped = _shipped_memories_root()
    existing_dirs = {os.path.normpath(p) for _, p in roots}
    if os.path.isdir(shipped) and os.path.normpath(shipped) not in existing_dirs:
        roots.append((None, os.path.normpath(shipped)))
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


def _plugin_json_name(plugin_json_path: str):
    """The `name` field of a `.claude-plugin/plugin.json` file, or None when
    the file is missing / unreadable / malformed."""
    try:
        with open(plugin_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (IOError, OSError, ValueError):
        return None
    name = data.get('name') if isinstance(data, dict) else None
    return name if isinstance(name, str) and name else None


def _is_plugin_source_repo(project_root: str, shipped_root: str) -> bool:
    """True when `project_root` IS the SWE plugin's own source checkout —
    i.e. the repo whose `.claude-plugin/plugin.json` `name` matches the
    shipped-memories plugin's own `.claude-plugin/plugin.json` `name`
    (sibling of `shipped_root`, the directory `_shipped_memories_root()`
    returned).

    Used to scope the plugin-SHIPPED `memories/` root's `paths:` globs
    (e.g. FEATURE_SWE's `hooks/**`) to the plugin source repo only — an
    unrelated project that happens to have a `hooks/` directory must NOT be
    told it needs FEATURE_SWE for editing it.
    """
    project_plugin_json = os.path.join(project_root, '.claude-plugin', 'plugin.json')
    shipped_plugin_json = os.path.join(
        os.path.dirname(os.path.normpath(shipped_root)), '.claude-plugin', 'plugin.json')
    if not os.path.isfile(project_plugin_json) or not os.path.isfile(shipped_plugin_json):
        return False
    project_name = _plugin_json_name(project_plugin_json)
    shipped_name = _plugin_json_name(shipped_plugin_json)
    return bool(project_name) and project_name == shipped_name


def _build_index(project_root: str):
    """Scan feature/*.md and dev/*.md under every memory root; return a list
    of (memory_name, globs) tuples. Cached per project_root.

    The plugin's SHIPPED `memories/` root (see `_shipped_memories_root`) is
    SKIPPED entirely unless `project_root` IS the plugin source repo itself
    (see `_is_plugin_source_repo`) — its `paths:` globs (e.g. FEATURE_SWE's
    `hooks/**`, `skills/swe-*/**`) describe the plugin's OWN source tree and
    must not leak into an unrelated project that merely has a same-named
    directory (e.g. any project with a `hooks/` dir). This skip applies ONLY
    to the paths:-glob index built here; `memory_roots()` and
    `memory_exists()` keep resolving shipped memories by name for every
    project.
    """
    if project_root in _INDEX_CACHE:
        return _INDEX_CACHE[project_root]

    shipped_root = os.path.normpath(_shipped_memories_root())
    scope_shipped = _is_plugin_source_repo(project_root, shipped_root)

    index = []
    for alias, root_dir in memory_roots(project_root):
        if (not scope_shipped) and os.path.normpath(root_dir) == shipped_root:
            continue
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


def fallback_dev_docs(rel_path: str, project_root: str) -> list:
    """Extension-based dev-standards fallback for `rel_path` (relative to
    `project_root`, '/'-separated).

    Looks up `rel_path`'s suffix in `EXTENSION_LANGUAGE_FALLBACK` (longest
    suffix matched first, e.g. '.blade.php' before '.php') and returns every
    `dev/DEV_<KEY>` among that extension's candidate language keys that
    `memory_exists`, PLUS `feature/FEATURE_DEV_STANDARDS` when it exists.
    Returns [] when the extension is unknown or none of the candidate
    memories exist.

    This is a STANDALONE lookup — callers decide WHEN to apply it (see
    `required_docs_for_path`'s "no paths:-matched dev/* name" condition).
    """
    rel_path = str(rel_path or '').replace('\\', '/').lower()
    for suffix, candidates in _EXTENSION_LANGUAGE_FALLBACK_SORTED:
        if not rel_path.endswith(suffix):
            continue
        found = []
        for key in candidates:
            name = f'dev/DEV_{key}'
            if memory_exists(name, project_root):
                found.append(name)
        if found and memory_exists('feature/FEATURE_DEV_STANDARDS', project_root):
            found.append('feature/FEATURE_DEV_STANDARDS')
        return found
    return []


def required_docs_for_path(file_path: str, project_root: str) -> list:
    """Memories required for editing `file_path`, sorted and de-duplicated.

    file_path is made relative to project_root before glob matching (an
    already-relative path is used as-is). A feature/dev memory is required
    when ANY of its `paths:` globs matches. When file_path is a test
    artifact (is_test_target), 'feature/FEATURE_TESTS' and 'dev/DEV_TESTS'
    are added too, filtered by memory_exists (never demand a doc the project
    does not have).

    When the paths:-matched set contains NO `dev/*` name (no dev-standards
    memory's `paths:` front-matter covers this file — including the case
    where no dev-standards memories exist at all, or they exist with no
    `paths:` block), `fallback_dev_docs` is consulted and its names are
    added too — this is what makes editing e.g. a `.php` file demand
    `dev/DEV_PHP` even when that memory carries no `paths:` glob of its own.
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

    has_dev_match = any(n == 'dev' or n.startswith('dev/') or '/dev/' in n for n in required)
    if not has_dev_match:
        required.update(fallback_dev_docs(rel_path, project_root))

    if is_test_target(rel_path):
        for name in TEST_DOC_NAMES:
            if memory_exists(name, project_root):
                required.add(name)

    return sorted(required)


def _read_memory_text(name: str, project_root: str):
    """Raw file content for memory `name` (see memory_exists' name grammar),
    or None when it does not exist / cannot be read."""
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
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    return f.read()
            except OSError:
                return None
    return None


def read_obligations(name: str, project_root: str) -> list:
    """The memory's front-matter `obligations:` list items, or [] when the
    memory is missing, has no front-matter, or declares `obligations: []`.

    Reuses parse_paths_frontmatter's block/inline-list grammar (via
    _extract_key_list) rather than re-implementing YAML-lite parsing —
    single source of truth for the front-matter list shapes this module
    understands.
    """
    text = _read_memory_text(name, project_root)
    if not text:
        return []
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return []
    fm_lines = m.group(1).splitlines()
    return _extract_key_list(fm_lines, 'obligations', top_level=True)


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
