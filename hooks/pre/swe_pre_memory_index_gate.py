#!/usr/bin/env python3
"""PreToolUse hook — HARD-DENY non-indexed category links entering MEMORY.md.

MEMORY.md is the auto-loaded session index. spec/report/research/project
memories are browsed via list_memories(topic=...) and are NEVER indexed there —
an indexed spec rides into every session's context and gets read as general
feature knowledge (the exact leak this gate closes).

swe_post_memory_index.py already states the rule but is PostToolUse-advisory:
it cannot deny, and it only fires on write_memory — index edits made via
edit_memory or raw Edit/Write slipped through. This gate runs BEFORE the write
and denies it, state-independently.

Matches: write_memory / edit_memory (Serena, both server prefixes) + Edit/Write.
Fires ONLY when the target is the MEMORY index AND the written content
introduces a link into a non-indexed category. Everything else passes silently.

SECOND DUTY (B4) — new-memory dedupe: a write_memory that CREATES a memory
(name not on disk under .serena/memory/**, .serena/memories/** or memories/**)
is denied when an existing memory already covers its topic — the dumb check:
every distinctive (>= 4 char) token of the new name (dir + REF_/SPEC_/DOM_/
FEATURE_/SYS_ prefixes stripped) appears in one existing memory's basename or
body. The remedy is edit_memory on the hit, not a near-duplicate file; the
literal tag [new-memory-justified: <reason>] in the content overrides. Edits/
overwrites of EXISTING memories and WM_ session files always pass.

THIRD DUTY (Change Set H) — obligations-digest enforcement: a write_memory (or
direct Write of a *.md under a /.serena/memory/ path) that CREATES or
OVERWRITES a memory under a rule-bearing prefix (dom/, ref/, dev/, feature/)
is denied when the content's front-matter carries no `obligations:` field.
`obligations: []` is the conscious-none escape and always passes. edit_memory
(partial edits) and non-rule-bearing prefixes are never denied by this check.
The digest this field captures is what the two-tier sweep (wm_server
_check_memory_sweep) plans obligations from without a full body read.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# Categories that must never appear as MEMORY.md index links. Keep in sync with
# NON_INDEXED_CATEGORIES in hooks/post/swe_post_memory_index.py.
NON_INDEXED_CATEGORIES = ("spec", "report", "research", "project")

# Markdown link whose target is inside a non-indexed topic dir, e.g.
# "](spec/SPEC_X.md)" or "](.serena/memory/report/REPORT_Y.md)".
_CATEGORY_DIR_LINK = re.compile(
    r"\]\(\s*[^)]*\b(?:%s)/" % "|".join(NON_INDEXED_CATEGORIES), re.IGNORECASE
)
# Markdown link to a category file by bare basename, e.g. "](SPEC_X.md)".
_CATEGORY_FILE_LINK = re.compile(
    r"\]\(\s*[^)/]*\b(?:SPEC|REPORT|RESEARCH|PROJECT)_[^)]*\.md\s*\)"
)

# Content-bearing fields across the matched tools:
#   write_memory: content · edit_memory: repl · Edit: new_string · Write: content
CONTENT_FIELDS = ("content", "repl", "new_string")

# ---------------------------------------------------------------------------
# B4 — new-memory dedupe
# ---------------------------------------------------------------------------
# Memory trees scanned for existing memories, relative to the session cwd.
MEMORY_DIR_NAMES = (".serena/memory", ".serena/memories", "memories")

# Type prefixes stripped off a basename before topic tokenization.
MEMORY_TYPE_PREFIXES = ("REF_", "SPEC_", "DOM_", "FEATURE_", "SYS_")

# Literal override tag: a deliberate, justified new memory passes the gate.
NEW_MEMORY_OVERRIDE_RE = re.compile(r"\[new-memory-justified:\s*[^\]]+\]")

# A topic token must be at least this long to count as distinctive.
_DISTINCTIVE_TOKEN_LEN = 4

# Body-scan cap per existing memory (bytes) — the scan stays cheap.
_BODY_SCAN_CAP = 65536

_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _strip_type_prefix(basename):
    """Strip one leading REF_/SPEC_/DOM_/FEATURE_/SYS_ type prefix."""
    for prefix in MEMORY_TYPE_PREFIXES:
        if basename.upper().startswith(prefix):
            return basename[len(prefix):]
    return basename


def memory_topic_tokens(memory_name):
    """Distinctive topic tokens of a memory name: basename only (dir prefix
    dropped), type prefix stripped, split on non-alphanumerics, lowercase,
    tokens shorter than 4 chars discarded."""
    base = str(memory_name).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    base = _strip_type_prefix(base)
    return {t for t in _TOKEN_SPLIT_RE.split(base.lower())
            if len(t) >= _DISTINCTIVE_TOKEN_LEN}


def _existing_memory_files(cwd):
    """Yield (tree_root, file_path) for every .md under the memory trees."""
    for rel_dir in MEMORY_DIR_NAMES:
        root = os.path.join(cwd, rel_dir)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if fname.endswith(".md"):
                    yield root, os.path.join(dirpath, fname)


def memory_exists(cwd, memory_name):
    """True when memory_name already exists on disk in any memory tree —
    by its exact relative path or by basename anywhere in a tree."""
    name = str(memory_name).replace("\\", "/").strip().strip("/")
    if name.endswith(".md"):
        name = name[:-3]
    target_base = name.rsplit("/", 1)[-1] + ".md"
    for root, path in _existing_memory_files(cwd):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel == name + ".md" or os.path.basename(path) == target_base:
            return True
    return False


def find_on_topic_memories(cwd, tokens, limit=5):
    """Existing memories that cover EVERY token — in their basename tokens or
    (cheap python scan, capped) their body. Returns tree-relative names
    without '.md'. MEMORY.md and WM_ session files never count as hits."""
    hits = []
    for root, path in _existing_memory_files(cwd):
        base = os.path.basename(path)
        if base == "MEMORY.md" or base.startswith("WM_"):
            continue
        base_tokens = memory_topic_tokens(base)
        uncovered = [t for t in tokens if t not in base_tokens]
        if uncovered:
            try:
                with open(path, "r", errors="replace") as f:
                    body = f.read(_BODY_SCAN_CAP).lower()
            except OSError:
                continue
            if any(t not in body for t in uncovered):
                continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        hits.append(rel[:-3] if rel.endswith(".md") else rel)
        if len(hits) >= limit:
            break
    return hits


def new_memory_dedupe_denial(tool_name, tool_input, cwd):
    """B4 verdict: the deny message, or None to allow.

    Applies ONLY to write_memory calls that would CREATE a new memory.
    Edits/overwrites of existing memories, WM_ session files, and content
    carrying the [new-memory-justified: <reason>] override always pass.
    """
    if not str(tool_name).endswith("write_memory"):
        return None
    tool_input = tool_input or {}
    name = str(tool_input.get("memory_name", "")).strip()
    if not name:
        return None
    if name.replace("\\", "/").rsplit("/", 1)[-1].startswith("WM_"):
        return None  # session working memory, not a knowledge memory
    if NEW_MEMORY_OVERRIDE_RE.search(str(tool_input.get("content", ""))):
        return None
    if not cwd or not os.path.isdir(cwd):
        return None
    if memory_exists(cwd, name):
        return None  # updating an existing memory always passes
    tokens = memory_topic_tokens(name)
    if not tokens:
        return None
    hits = find_on_topic_memories(cwd, tokens)
    if not hits:
        return None
    return (
        "🛑 BLOCKED: An on-topic memory already exists: {hits}. "
        "Update it (edit_memory {first}) instead of creating a duplicate. "
        "Override only with literal tag [new-memory-justified: <reason>] "
        "in the content.".format(hits=", ".join(hits), first=hits[0])
    )


# ---------------------------------------------------------------------------
# Change Set H — obligations-digest enforcement
# ---------------------------------------------------------------------------
# Prefixes that REQUIRE an `obligations:` front-matter field. All other
# prefixes (arch/, spec/, wf/, index/, sys/, feedback/, ...) are optional.
RULE_BEARING_PREFIXES = ("dom/", "ref/", "dev/", "feature/")

# Front-matter block: opening '---', then an `obligations:` key as a top-level
# sibling of `description:` (2-space-or-less indent, not nested under
# metadata:), before the closing '---'.
_FRONT_MATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_OBLIGATIONS_FIELD_RE = re.compile(r"^obligations:", re.MULTILINE)

OBLIGATIONS_FIELD_GRAMMAR = (
    "obligations:\n"
    "  - <imperative obligation, one line, concrete>\n"
    "(top-level sibling of `description`; `obligations: []` declares a "
    "conscious none)"
)


def _memory_prefix(memory_name_or_path):
    """Normalize a memory_name or file_path to its 'prefix/' dir segment
    (e.g. 'dom/', 'ref/'), or '' when there is no dir segment."""
    name = str(memory_name_or_path or "").replace("\\", "/").strip()
    # A file_path may carry the full .serena/memory/<prefix>/NAME.md shape —
    # take the segment immediately before the basename.
    parts = [p for p in name.split("/") if p]
    if len(parts) < 2:
        return ""
    return parts[-2].lower() + "/"


def _has_obligations_field(content):
    """True when the front-matter block contains a top-level `obligations:`
    field (list or `[]`)."""
    match = _FRONT_MATTER_BLOCK_RE.match(str(content or "").lstrip("﻿"))
    if not match:
        return False
    return bool(_OBLIGATIONS_FIELD_RE.search(match.group(1)))


def missing_obligations_reason(memory_name_or_path, content):
    """Return the deny message when `content` authors/overwrites a
    rule-bearing memory with no `obligations:` front-matter field, else None.

    Applies only to prefixes in RULE_BEARING_PREFIXES; callers are
    responsible for gating this to CREATE/overwrite (not edit_memory).
    """
    prefix = _memory_prefix(memory_name_or_path)
    if prefix not in RULE_BEARING_PREFIXES:
        return None
    if _has_obligations_field(content):
        return None
    return (
        "🛑 BLOCKED: \"{name}\" is a rule-bearing memory (prefix: {prefix}) "
        "with no `obligations:` front-matter field. Add it — a top-level "
        "sibling of `description`:\n{grammar}\n"
        "`obligations: []` is the conscious-none escape when this memory "
        "truly carries no obligations. This digest is what the two-tier "
        "sweep plans from without a full body read.".format(
            name=memory_name_or_path, prefix=prefix,
            grammar=OBLIGATIONS_FIELD_GRAMMAR,
        )
    )


def _is_memory_md_path_under_serena(file_path):
    """True when file_path looks like a *.md write under a /.serena/memory/
    tree (direct Write bypass of write_memory)."""
    p = str(file_path or "").replace("\\", "/")
    return bool(p) and p.endswith(".md") and "/.serena/memory/" in p


def obligations_denial_for_write(tool_name, tool_input):
    """Change Set H verdict for a write_memory or direct Write call, or None.

    write_memory: denies on CREATE or OVERWRITE (both are full authoring —
    edit_memory partial edits are exempt and never reach this check).
    Direct Write: denies when file_path is a *.md under a /.serena/memory/
    path (the write_memory bypass this gate also has to cover).
    """
    tool_input = tool_input or {}
    name = str(tool_name or "")
    if name.endswith("write_memory"):
        memory_name = tool_input.get("memory_name", "")
        content = tool_input.get("content", "")
        return missing_obligations_reason(memory_name, content)
    if name.endswith("Write") and not name.endswith("write_memory"):
        file_path = tool_input.get("file_path", "")
        if not _is_memory_md_path_under_serena(file_path):
            return None
        content = tool_input.get("content", "")
        return missing_obligations_reason(file_path, content)
    return None


def targets_memory_index(tool_input):
    """True when the call writes the MEMORY.md index (by memory name or path)."""
    memory_name = str(tool_input.get("memory_name", ""))
    if memory_name in ("MEMORY", "MEMORY.md"):
        return True
    file_path = str(tool_input.get("file_path", ""))
    return os.path.basename(file_path.replace("\\", "/")) == "MEMORY.md"


def written_category_links(tool_input):
    """Return the non-indexed categories the written content would link."""
    blob = " ".join(str(tool_input.get(k, "")) for k in CONTENT_FIELDS)
    found = set()
    for match in _CATEGORY_DIR_LINK.finditer(blob):
        seg = match.group(0).lower()
        for cat in NON_INDEXED_CATEGORIES:
            if cat + "/" in seg:
                found.add(cat)
    if _CATEGORY_FILE_LINK.search(blob):
        for cat in NON_INDEXED_CATEGORIES:
            if re.search(r"\]\([^)/]*\b%s_" % cat.upper(), blob):
                found.add(cat)
    return sorted(found)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = str(input_data.get("tool_name", ""))
        tool_input = input_data.get("tool_input", {}) or {}

        if not targets_memory_index(tool_input):
            # Change Set H — obligations-digest enforcement: runs first, in
            # addition to (not instead of) the B4 dedupe check below.
            obligations_denial = obligations_denial_for_write(tool_name, tool_input)
            if obligations_denial:
                output = HookOutput(event_name="PreToolUse")
                output.block(obligations_denial)
                output.output_and_exit()
                return

            # B4 — new-memory dedupe: deny a write_memory creating a memory
            # whose topic an existing memory already covers.
            cwd = str(input_data.get("cwd", "") or "") or os.getcwd()
            denial = new_memory_dedupe_denial(tool_name, tool_input, cwd)
            if denial:
                output = HookOutput(event_name="PreToolUse")
                output.block(denial)
                output.output_and_exit()
                return
            output_empty()
            return

        leaked = written_category_links(tool_input)
        if not leaked:
            output_empty()
            return

        output = HookOutput(event_name="PreToolUse")
        output.block(
            "🛑 BLOCKED: this write adds {cats} link(s) to MEMORY.md.\n"
            "MEMORY.md is the auto-loaded session index — spec/report/research/"
            "project memories are NEVER indexed there. They are discovered via "
            "list_memories(topic=\"spec\"|\"report\"|\"research\"|\"project\") "
            "when a task explicitly needs them.\n"
            "Remove the {cats} link(s) from your update and re-issue it; the "
            "memory itself stays where it is.".format(cats="/".join(leaked))
        )
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Memory-index gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == "__main__":
    main()
