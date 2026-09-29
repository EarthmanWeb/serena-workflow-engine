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
  python3 scripts/validate-memory-graph.py [--root memories] [--root .serena/memory] [--json]

Exit code 1 if any dangling links are found, else 0.
"""

import argparse
import json
import os
import re
import sys

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


def find_memory_files(root: str):
    """Yield (relative_dir_prefixed_name, absolute_path) for every .md memory file under root."""
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
            yield prefixed, name, abspath


def build_index(roots):
    """Build a name -> [abspath,...] index. Keys include both the bare name
    and the dir-prefixed name, so links can be written either way."""
    index = {}
    files = []  # list of (prefixed_name, bare_name, abspath, root)
    for root in roots:
        if not os.path.isdir(root):
            continue
        for prefixed, bare, abspath in find_memory_files(root):
            files.append((prefixed, bare, abspath, root))
            index.setdefault(prefixed, []).append(abspath)
            index.setdefault(bare, []).append(abspath)
    return index, files


def extract_links(text: str):
    """Return the set of raw link tokens found in text (before placeholder filtering)."""
    links = set()
    links.update(LINK_MEM_RE.findall(text))
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

    inbound = {prefixed: 0 for prefixed, _, _, _ in files}

    for prefixed, bare, abspath, root in files:
        try:
            with open(abspath, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as e:
            dangling.append((prefixed, f"<unreadable: {e}>"))
            continue

        word_counts[prefixed] = len(text.split())
        caps_counts[prefixed] = {tok: text.count(tok) for tok in CAPS_TOKENS if text.count(tok)}

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
        if inbound.get(prefixed, 0) == 0:
            orphans.append(prefixed)

    return {
        "dangling": sorted(set(dangling)),
        "orphans": sorted(orphans),
        "word_counts": word_counts,
        "caps_counts": caps_counts,
        "file_count": len(files),
    }


def main():
    parser = argparse.ArgumentParser(description="Validate the memory link graph.")
    parser.add_argument(
        "--root",
        action="append",
        dest="roots",
        default=None,
        help="Memory root directory (repeatable). Default: memories",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args()

    roots = args.roots or ["memories"]

    result = validate(roots)

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Scanned {result['file_count']} memory files under: {', '.join(roots)}")
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
