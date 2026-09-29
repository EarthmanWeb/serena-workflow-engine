#!/usr/bin/env python3
"""Wrapper that patches Serena's memory name resolution before starting.

Adds automatic directory-prefix resolution for memory names:
  SYS_BUILDER_WYSIWYG  ->  sys/SYS_BUILDER_WYSIWYG
  DOM_BUILDER_BLOCKS   ->  dom/DOM_BUILDER_BLOCKS
  FEATURE_SWE          ->  feature/FEATURE_SWE

Also corrects wrong prefixes:
  feature/DOM_X        ->  dom/DOM_X

The prefix is derived from the first segment before '_', lowercased.
Falls back to flat file lookup if prefix directory doesn't contain the file.
Writes to new memories auto-resolve to the correct prefix directory.

Also guarantees standard YAML front matter on save (structure + directory-derived
metadata.type), so memories stay discoverable via search_memories_by_front_matter. The
LLM still authors name/description (WriteMemoryTool docstring + WF_INIT); this makes the
block and its type a hard guarantee. WM_/wf/claude/lite memories are exempt.
"""

import re
import sys

# Upstream (oraios) moved memory management out of serena.project.MemoriesManager
# into serena.memories.memory_manager.MemoryManager, and renamed the existing-file
# lookup _find_memory -> _find_existing_memory. Import the current class and method.
from serena.memories.memory_manager import MemoryManager

_original_find_memory = MemoryManager._find_existing_memory
_original_get_memory_file_path = MemoryManager.get_memory_file_path
_original_load_memory = MemoryManager.load_memory
_original_save_memory = MemoryManager.save_memory
_original_delete_memory = MemoryManager.delete_memory
_original_move_memory = MemoryManager.move_memory


# Prefixes whose files live flat in .serena/memories/ (not in swe/ subfolders)
_MEMORIES_DIR_PREFIXES = frozenset(["wm", "lite"])

# Directory prefix -> front-matter metadata.type. Mirrors the mapping documented in the
# /swe-memory-frontmatter skill. A prefix not listed here uses itself as the type.
_PREFIX_TO_TYPE = {
    "ref": "reference",
    "feedback": "feedback",
    "project": "project",
    "feature": "feature",
    "dom": "domain",
    "sys": "system",
    "arch": "architecture",
    "spec": "spec",
    "report": "report",
    "research": "research",
    "content": "content",
    "wf": "workflow",
}

# Memories that must NOT be auto-front-mattered on save: ephemeral working memory and the
# read-only workflow/obligation memories (WM_* live flat; wf/ and claude/ are read-only).
_NO_FRONTMATTER_PREFIXES = frozenset(["wm", "lite", "wf", "claude"])


def _split_alias(self, name):
    """Split an aliased memory name into ``(alias, remainder)``.

    An aliased memory (from ``--memory-path``/``.serena/memory-paths.conf`` entries
    of the form ``alias=path[:ro]``) is addressed ONLY as ``<alias>/<rel>``, e.g.
    ``em/feature/FEATURE_TESTS``. The alias segment must never be treated as a
    directory prefix by ``_normalize_name``/``_derive_type`` — those apply only to
    the remainder after the alias.

    Uses ``getattr(self, "_memory_aliases", {})`` so this keeps working against an
    older Serena fork that predates the aliasing feature (version-compat guard, not
    a behavioral fallback): with no ``_memory_aliases`` attribute, every name is
    treated as non-aliased, matching the pre-alias behavior exactly.

    Returns ``(None, clean_name)`` when ``name`` is not aliased, or
    ``(alias, remainder)`` when its first segment is a registered alias.
    """
    clean = name.replace(".md", "")
    aliases = getattr(self, "_memory_aliases", None)
    if not aliases or "/" not in clean:
        return None, clean
    first, remainder = clean.split("/", 1)
    if first in aliases:
        return first, remainder
    return None, clean


def _derive_prefix(name):
    """Derive the directory prefix from a memory name convention.

    E.g. DOM_BUILDER_BLOCKS -> dom, SYS_BUILDER_WYSIWYG -> sys,
         FEATURE_SWE -> feature, SPEC_EMAIL -> spec, WM_abc123 -> wm
    """
    clean = name.replace(".md", "")
    # Strip any existing directory prefix to get the base name
    base = clean.split("/")[-1] if "/" in clean else clean
    if "_" not in base or base.startswith("_"):
        return None
    return base.split("_")[0].lower()


def _derive_type(name):
    """Map a memory name's directory prefix to its front-matter metadata.type."""
    prefix = _derive_prefix(name)
    if prefix is None:
        return None
    return _PREFIX_TO_TYPE.get(prefix, prefix)


def _ensure_front_matter(name, content):
    """Guarantee ``content`` starts with a standard front-matter block.

    Belt-and-suspenders half of the front-matter policy: the LLM is instructed (WriteMemoryTool
    docstring + WF_INIT) to author ``name``/``description``; this makes the *structure* and the
    directory-derived ``metadata.type`` a hard guarantee regardless.

    - No front matter -> inject a block (name from the H1/base name, a placeholder description the
      author/backfill skill can improve, and the derived type).
    - Existing front matter -> leave the author's name/description untouched, but ensure a
      ``metadata:``/``type`` reflecting the directory is present (add it if missing). Never rewrites
      an author-provided description.

    Returns the (possibly unchanged) content.
    """
    mtype = _derive_type(name)
    if mtype is None:
        return content  # can't classify (e.g. MEMORY) — leave as-is

    if content.startswith("---"):
        # Existing block: only guarantee a type is present; do not touch name/description.
        head, sep, _body = content.partition("\n---")
        if not sep:
            return content  # malformed/unterminated — don't risk mangling it
        if re.search(r"(?m)^\s*type\s*:", head):
            return content  # some type already declared (flat or nested) — respect it
        # No type anywhere in the block: append a nested metadata.type before the closing fence.
        return f"{head}\nmetadata:\n  type: {mtype}\n---{content[len(head) + len(sep):]}"

    # No front matter at all: derive a name and inject a full block above the existing content.
    base = name.replace(".md", "").split("/")[-1]
    h1 = re.match(r"\s*#\s+(.+)", content)
    derived_name = h1.group(1).strip() if h1 else base
    block = (
        "---\n"
        f"name: {derived_name}\n"
        "description: TODO — one sentence describing what this memory is about.\n"
        "metadata:\n"
        f"  type: {mtype}\n"
        "---\n\n"
    )
    return block + content


def _normalize_remainder(clean):
    """Normalize a (possibly already alias-stripped) name to the correct prefix.

    ``clean`` must already have ``.md`` stripped and, for an aliased name, the
    ``<alias>/`` segment already removed. Handles:
      DOM_X              -> dom/DOM_X        (missing prefix, swe subdir)
      feature/DOM_X      -> dom/DOM_X        (wrong prefix)
      dom/DOM_X          -> dom/DOM_X        (already correct)
      WM_abc123          -> WM_abc123        (flat in memories/, no subdir)
      LITE_MODE_abc123   -> LITE_MODE_abc123 (flat in memories/, no subdir)
    """
    # Get the base filename without any directory
    base = clean.split("/")[-1] if "/" in clean else clean
    prefix = _derive_prefix(base)
    if prefix is None:
        return clean  # Can't derive prefix (e.g. MEMORY.md)
    # WM and LITE files live flat in .serena/memories/ — no subdirectory
    if prefix in _MEMORIES_DIR_PREFIXES:
        return base
    return f"{prefix}/{base}"


def _normalize_name(self, name):
    """Normalize a memory name, preserving an ``<alias>/`` prefix untouched.

    Non-aliased names (or when ``self`` predates ``_memory_aliases``) behave
    exactly as before: the whole name is normalized by ``_normalize_remainder``.
    An aliased name (``em/feature/FEATURE_X``) keeps its ``em/`` segment and
    normalizes only the remainder, so aliased and primary copies of a
    same-named memory (``feature/FEATURE_X``) never collide.
    """
    alias, remainder = _split_alias(self, name)
    normalized_remainder = _normalize_remainder(remainder)
    if alias is None:
        return normalized_remainder
    return f"{alias}/{normalized_remainder}"


def _patched_find_memory(self, name):
    alias, _remainder = _split_alias(self, name)

    # Try the name as-is first (handles already-correct paths)
    try:
        result = _original_find_memory(self, name)
        if result is not None:
            return result
    except Exception:
        pass

    # Auto-resolve: normalize to correct prefix and retry
    normalized = _normalize_name(self, name)
    if normalized != name.replace(".md", ""):
        try:
            result = _original_find_memory(self, normalized)
            if result is not None:
                return result
        except Exception:
            pass

    # Bare base-name fallback is for non-aliased root-level files only — an
    # aliased name must never fall back to a non-aliased (primary) lookup, or
    # an aliased read/write would silently redirect to the primary copy.
    if alias is not None:
        return None

    clean = name.replace(".md", "")
    base = clean.split("/")[-1] if "/" in clean else None
    if base and base != clean:
        try:
            result = _original_find_memory(self, base)
            if result is not None:
                return result
        except Exception:
            pass

    return None


def _patched_get_memory_file_path(self, name):
    # If memory already exists somewhere, update in-place
    existing = self._find_existing_memory(name)
    if existing is not None:
        return existing

    # New memory: auto-resolve to correct prefix directory
    normalized = _normalize_name(self, name)
    # Delegate to original with the normalized (alias-preserving) name
    return _original_get_memory_file_path(self, normalized)


def _patched_load_memory(self, name):
    """Normalize name before reading."""
    alias, _remainder = _split_alias(self, name)

    # Try as-is first
    try:
        return _original_load_memory(self, name)
    except Exception:
        pass
    # Try normalized
    normalized = _normalize_name(self, name)
    if normalized != name.replace(".md", ""):
        try:
            return _original_load_memory(self, normalized)
        except Exception:
            pass

    # Bare base-name fallback is for non-aliased names only — see
    # _patched_find_memory for why an aliased name must never fall back to a
    # non-aliased (primary) lookup.
    if alias is not None:
        return _original_load_memory(self, normalized)

    # Try bare name
    clean = name.replace(".md", "")
    base = clean.split("/")[-1] if "/" in clean else None
    if base and base != clean:
        try:
            return _original_load_memory(self, base)
        except Exception:
            pass
    # Final: let original raise its error with the normalized name
    return _original_load_memory(self, normalized if normalized != name.replace(".md", "") else name)


def _patched_save_memory(self, name, content, is_tool_context=False):
    """Normalize name before writing, and guarantee standard front matter on the content."""
    normalized = _normalize_name(self, name)
    _alias, remainder = _split_alias(self, normalized)
    prefix = _derive_prefix(remainder)
    if prefix not in _NO_FRONTMATTER_PREFIXES:
        # Front-matter type derivation must use the remainder (post-alias-strip),
        # not the alias segment, so it never uses an alias name as its prefix.
        content = _ensure_front_matter(remainder, content)
    return _original_save_memory(self, normalized, content, is_tool_context)


def _patched_delete_memory(self, name, is_tool_context=False):
    """Normalize name before deleting."""
    try:
        return _original_delete_memory(self, name, is_tool_context)
    except Exception:
        pass
    normalized = _normalize_name(self, name)
    return _original_delete_memory(self, normalized, is_tool_context)


def _patched_move_memory(self, old_name, new_name, is_tool_context=False):
    """Normalize names before moving/renaming."""
    normalized_old = _normalize_name(self, old_name)
    normalized_new = _normalize_name(self, new_name)
    return _original_move_memory(self, normalized_old, normalized_new, is_tool_context)


MemoryManager._find_existing_memory = _patched_find_memory
MemoryManager.get_memory_file_path = _patched_get_memory_file_path
MemoryManager.load_memory = _patched_load_memory
MemoryManager.save_memory = _patched_save_memory
MemoryManager.delete_memory = _patched_delete_memory
MemoryManager.move_memory = _patched_move_memory

# Delegate to Serena CLI with start-mcp-server prepended
sys.argv = ["serena", "start-mcp-server"] + sys.argv[1:]

from serena.cli import top_level  # noqa: E402

top_level()
