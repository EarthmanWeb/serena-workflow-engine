#!/usr/bin/env python3
"""Validate the memory link graph under one or more memory roots.

Parses links of the forms:
  - mem:<name>
  - [[name]]
  - `NAME` where NAME matches ^(WF|REF|DOM|ARCH|FEATURE|SYS|SPEC|INDEX|CLAUDE|DEV)_[A-Z0-9_]+$

Resolves each link against the memory files found under the given root(s),
matching with or without a directory prefix (e.g. "wf/WF_INIT" or "WF_INIT").

Reports:
  - dangling links (ERROR) — link resolves to no known memory
  - orphans (WARNING) — memory with zero inbound links from any other memory
  - per-file word counts (INFO)
  - per-file CAPS hard-stop counts: NEVER/MUST/ALWAYS/CRITICAL/⛔ (INFO)

Usage:
  python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py [--root memories] [--root .serena/memory] [--json]
  python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py --root em=../em-serena/.serena/memory
  python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py                       # uses .serena/memory-paths.conf
  python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py --plugin-root /path/to/plugin/memories
  python3 skills/swe-memory-size-audit/scripts/validate-memory-graph.py --extra-root memories  # + conf roots, e.g. inside the plugin source repo

Root parsing matches scripts/memory-size-audit.py: --root accepts a plain
DIR or an aliased "alias=DIR" (aliased memories resolve with an
"<alias>/<rel>" prefix). With no --root at all, roots are read from
".serena/memory-paths.conf" in the current working directory (same file
format memory-size-audit.py uses). --plugin-root DIR is shorthand for an
extra unaliased --root pointing at the shipped plugin memories/ tree — pass
it alongside every project-side root in ONE invocation, since links cross
trees (a project's .serena/memory commonly links to the plugin's
wf/dom/feature memories) and validating roots separately reports false
dangling links. --extra-root [alias=]DIR (repeatable) appends ON TOP OF
whichever roots were resolved above (explicit --root args, or else the conf
file) instead of replacing them — use it to add the plugin source repo's own
"memories" tree without losing the conf-derived project roots. Passing an
explicit --root REPLACES the conf default entirely, so combining the
plugin's own tree with conf roots must go through --extra-root or
--plugin-root, never a bare --root.

Exit code 1 if any dangling links are found, else 0.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        "hooks",
    ),
)
from swe_hooks.core.memory_size import (  # noqa: E402
    CONF_PATH,
    EXCLUDED_TOPICS,
    parse_root_arg,
    resolve_roots as _resolve_roots,
    is_excluded_memory,
)

EXCLUDED_TOPICS_LABEL = ", ".join(f"{t}/" for t in EXCLUDED_TOPICS)

LINK_MEM_RE = re.compile(r"mem:([A-Za-z0-9_./-]+)")
LINK_WIKI_RE = re.compile(r"\[\[([A-Za-z0-9_./-]+)\]\]")
LINK_BARE_RE = re.compile(
    r"`((?:WF|REF|DOM|ARCH|FEATURE|SYS|SPEC|INDEX|CLAUDE|DEV)_[A-Z0-9_]+)`"
)

CAPS_TOKENS = ("NEVER", "MUST", "ALWAYS", "CRITICAL", "⛔")

# Known placeholder / pattern tokens that are never real memory names.
PLACEHOLDER_SUFFIX_UNDERSCORE = re.compile(r"_$")
KNOWN_PATTERN_PREFIXES = (
    "DEV_",  # DEV_* language-standard memories, generated per-project (not shipped source)
)
KNOWN_PATTERN_TOKENS = {
    "FEATURE_[KEY]",
    "FEATURE_KEY",
}
# Bare-word wiki-link examples used to illustrate the [[link]] syntax itself,
# not actual links (e.g. "the `[[link]]` closure", "`[[linked]]` memory names").
WIKI_SYNTAX_EXAMPLES = {"link", "links", "linked"}

# Memories the init/bootstrap templates generate per-project. They live only
# in an initialized project's own memory tree, not in the shipped plugin
# source tree scanned here, so they legitimately do not resolve here.
PROJECT_GENERATED_NAMES = {
    "INDEX_FEATURES",
    "index/INDEX_FEATURES",
}


def is_placeholder(name: str) -> bool:
    """True if `name` is a template placeholder, not a real memory link."""
    if any(ch in name for ch in "[]<>"):
        return True
    if PLACEHOLDER_SUFFIX_UNDERSCORE.search(name):
        return True
    if name in KNOWN_PATTERN_TOKENS:
        return True
    if any(name == p.rstrip("_") or name.startswith(p) for p in KNOWN_PATTERN_PREFIXES):
        return True
    if name.rsplit("/", 1)[-1] in WIKI_SYNTAX_EXAMPLES:
        return True
    if name in PROJECT_GENERATED_NAMES:
        return True
    # Bare "ARCH__" / "REF__" style double-underscore stubs used as
    # illustrative placeholders in tables.
    if "__" in name:
        return True
    return False


def find_memory_files(root: str, alias: str = None):
    """Yield (relative_dir_prefixed_name, absolute_path) for every .md memory file under root.

    `alias`, when given, prefixes every name "<alias>/<rel>" (matching
    scripts/memory-size-audit.py's aliased-root naming), so links from an
    aliased tree are addressed as "<alias>/<rel>".
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden/version-control dirs.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            name = fname[:-3]
            abspath = os.path.join(dirpath, fname)
            rel_dir = os.path.relpath(dirpath, root)
            if rel_dir == ".":
                prefixed = name
            else:
                prefixed = f"{rel_dir}/{name}".replace(os.sep, "/")
            if alias:
                prefixed = f"{alias}/{prefixed}"
                name = f"{alias}/{name}"
            yield prefixed, name, abspath


def _normalize_roots(roots):
    """Normalize a roots list to (alias_or_None, dir) tuples.

    Accepts plain dir strings (no alias) or (alias, dir) tuples, so callers
    that already resolved aliased --root/conf entries can pass them through
    unchanged.
    """
    normalized = []
    for r in roots:
        if isinstance(r, (tuple, list)):
            normalized.append((r[0], r[1]))
        else:
            normalized.append((None, r))
    return normalized


def build_index(roots):
    """Build a name -> [abspath,...] index. Keys include both the bare name
    and the dir-prefixed name, so links can be written either way.

    `roots` — plain dir strings, or (alias_or_None, dir) tuples (see
    _normalize_roots).
    """
    index = {}
    files = []  # list of (prefixed_name, bare_name, abspath, root)
    for alias, root in _normalize_roots(roots):
        if not os.path.isdir(root):
            continue
        for prefixed, bare, abspath in find_memory_files(root, alias=alias):
            files.append((prefixed, bare, abspath, root))
            index.setdefault(prefixed, []).append(abspath)
            index.setdefault(bare, []).append(abspath)
    return index, files


def extract_links(text: str):
    """Return the set of raw link tokens found in text (before placeholder filtering)."""
    links = set()
    links.update(
        m.rstrip("./-") for m in LINK_MEM_RE.findall(text)
    )
    links.update(LINK_WIKI_RE.findall(text))
    links.update(LINK_BARE_RE.findall(text))
    return links


def normalize_link(link: str) -> str:
    """Strip a leading/trailing slash or trailing .md some link styles include."""
    link = link.strip()
    if link.endswith(".md"):
        link = link[:-3]
    return link.strip("/")


def validate(roots):
    """Run the graph validation. Returns a result dict."""
    index, files = build_index(roots)

    dangling = []   # (file, link)
    orphans = []    # prefixed_name with zero inbound links
    word_counts = {}
    caps_counts = {}
    excluded_count = 0

    inbound = {prefixed: 0 for prefixed, _, _, _ in files}

    for prefixed, bare, abspath, root in files:
        if is_excluded_memory(prefixed):
            excluded_count += 1

        try:
            with open(abspath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            if not is_excluded_memory(prefixed):
                dangling.append((prefixed, f"<unreadable: {e}>"))
            continue

        word_counts[prefixed] = len(text.split())
        caps_counts[prefixed] = {tok: text.count(tok) for tok in CAPS_TOKENS if text.count(tok)}

        if is_excluded_memory(prefixed):
            # Excluded memories are not validated as link SOURCES: their
            # outbound links (dangling or not) are not reported. They still
            # count as valid link TARGETS via `index` above, and their word
            # counts / caps counts are still reported (informational only).
            continue

        raw_links = extract_links(text)
        for raw in raw_links:
            link = normalize_link(raw)
            if not link or is_placeholder(link):
                continue
            if link == prefixed or link == bare:
                # Self-link (e.g. a file naming itself in front-matter) — not an edge.
                continue
            if link in index:
                # Mark inbound credit on every file matching that name.
                for target_path in index[link]:
                    for p2, b2, ap2, r2 in files:
                        if ap2 == target_path:
                            inbound[p2] += 1
            else:
                dangling.append((prefixed, link))

    for prefixed, _, _, _ in files:
        if is_excluded_memory(prefixed):
            continue
        if inbound.get(prefixed, 0) == 0:
            orphans.append(prefixed)

    return {
        "dangling": sorted(set(dangling)),
        "orphans": sorted(orphans),
        "word_counts": word_counts,
        "caps_counts": caps_counts,
        "file_count": len(files),
        "excluded": excluded_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Validate the memory link graph.")
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=None,
        help="Memory root directory, optionally '[alias=]DIR' (repeatable). "
        "Default: .serena/memory-paths.conf in cwd, else 'memories'.",
    )
    parser.add_argument(
        "--plugin-root",
        dest="plugin_root",
        default=None,
        help="Shorthand for an extra unaliased --root pointing at the shipped "
        "plugin memories/ tree (e.g. ${CLAUDE_PLUGIN_ROOT}/memories). Pass it "
        "alongside every project-side root in one invocation — links cross trees.",
    )
    parser.add_argument(
        "--extra-root",
        action="append",
        dest="extra_roots",
        default=None,
        help="An additional root (optionally '[alias=]DIR', repeatable) appended "
        "ON TOP OF the roots resolved above (--root args, or else "
        ".serena/memory-paths.conf), instead of replacing them. Use this to add "
        "the plugin source repo's own 'memories' tree when auditing inside that "
        "repo, without losing the conf-derived project roots.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args()

    if args.roots:
        roots = [parse_root_arg(r) for r in args.roots]
    else:
        conf_roots = _resolve_roots(None, CONF_PATH)
        roots = conf_roots if conf_roots else [(None, "memories")]

    if args.plugin_root:
        roots.append((None, args.plugin_root))

    if args.extra_roots:
        roots.extend(parse_root_arg(r) for r in args.extra_roots)

    root_labels = [f"{a}={d}" if a else d for a, d in roots]

    result = validate(roots)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"Scanned {result['file_count']} memory files under: {', '.join(root_labels)} "
            f"(excluded={result['excluded']}: {EXCLUDED_TOPICS_LABEL})"
        )
        print()
        if result["dangling"]:
            print(f"ERROR: {len(result['dangling'])} dangling link(s):")
            for src, link in result["dangling"]:
                print(f"  {src} -> {link}")
        else:
            print("OK: no dangling links.")
        print()
        if result["orphans"]:
            print(f"WARNING: {len(result['orphans'])} orphan memory file(s) (no inbound links):")
            for o in result["orphans"]:
                print(f"  {o}")
        else:
            print("OK: no orphan memory files.")
        print()
        print("INFO: word counts")
        for name, count in sorted(result["word_counts"].items()):
            print(f"  {name}: {count}")
        print()
        print("INFO: CAPS hard-stop counts (NEVER/MUST/ALWAYS/CRITICAL/⛔)")
        for name, counts in sorted(result["caps_counts"].items()):
            if counts:
                total = sum(counts.values())
                detail = ", ".join(f"{k}={v}" for k, v in counts.items())
                print(f"  {name}: {total} ({detail})")

    return 1 if result["dangling"] else 0


if __name__ == "__main__":
    sys.exit(main())
