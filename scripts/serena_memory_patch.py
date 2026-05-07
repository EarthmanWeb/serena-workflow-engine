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
"""

import sys

from serena.project import MemoriesManager

_original_find_memory = MemoriesManager._find_memory
_original_get_memory_file_path = MemoriesManager.get_memory_file_path
_original_load_memory = MemoriesManager.load_memory
_original_save_memory = MemoriesManager.save_memory
_original_delete_memory = MemoriesManager.delete_memory
_original_move_memory = MemoriesManager.move_memory


# Prefixes whose files live flat in .serena/memories/ (not in swe/ subfolders)
_MEMORIES_DIR_PREFIXES = frozenset(["wm", "lite"])

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


def _normalize_name(name):
    """Normalize a memory name to use the correct directory prefix.

    Handles:
      DOM_X              -> dom/DOM_X        (missing prefix, swe subdir)
      feature/DOM_X      -> dom/DOM_X        (wrong prefix)
      dom/DOM_X          -> dom/DOM_X        (already correct)
      WM_abc123          -> WM_abc123        (flat in memories/, no subdir)
      LITE_MODE_abc123   -> LITE_MODE_abc123 (flat in memories/, no subdir)
    """
    clean = name.replace(".md", "")
    # Get the base filename without any directory
    base = clean.split("/")[-1] if "/" in clean else clean
    prefix = _derive_prefix(base)
    if prefix is None:
        return clean  # Can't derive prefix (e.g. _INDEX)
    # WM and LITE files live flat in .serena/memories/ — no subdirectory
    if prefix in _MEMORIES_DIR_PREFIXES:
        return base
    correct = f"{prefix}/{base}"
    return correct


def _patched_find_memory(self, name):
    # Try the name as-is first (handles already-correct paths)
    try:
        result = _original_find_memory(self, name)
        if result is not None:
            return result
    except Exception:
        pass

    # Auto-resolve: normalize to correct prefix and retry
    normalized = _normalize_name(name)
    if normalized != name.replace(".md", ""):
        try:
            result = _original_find_memory(self, normalized)
            if result is not None:
                return result
        except Exception:
            pass

    # Also try the bare name without any prefix (for root-level files)
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
    existing = self._find_memory(name)
    if existing is not None:
        return existing

    # New memory: auto-resolve to correct prefix directory
    normalized = _normalize_name(name)
    # Delegate to original with the normalized (prefixed) name
    return _original_get_memory_file_path(self, normalized)


def _patched_load_memory(self, name):
    """Normalize name before reading."""
    # Try as-is first
    try:
        return _original_load_memory(self, name)
    except Exception:
        pass
    # Try normalized
    normalized = _normalize_name(name)
    if normalized != name.replace(".md", ""):
        try:
            return _original_load_memory(self, normalized)
        except Exception:
            pass
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
    """Normalize name before writing."""
    normalized = _normalize_name(name)
    return _original_save_memory(self, normalized, content, is_tool_context)


def _patched_delete_memory(self, name, is_tool_context=False):
    """Normalize name before deleting."""
    try:
        return _original_delete_memory(self, name, is_tool_context)
    except Exception:
        pass
    normalized = _normalize_name(name)
    return _original_delete_memory(self, normalized, is_tool_context)


def _patched_move_memory(self, old_name, new_name, is_tool_context=False):
    """Normalize names before moving/renaming."""
    normalized_old = _normalize_name(old_name)
    normalized_new = _normalize_name(new_name)
    return _original_move_memory(self, normalized_old, normalized_new, is_tool_context)


MemoriesManager._find_memory = _patched_find_memory
MemoriesManager.get_memory_file_path = _patched_get_memory_file_path
MemoriesManager.load_memory = _patched_load_memory
MemoriesManager.save_memory = _patched_save_memory
MemoriesManager.delete_memory = _patched_delete_memory
MemoriesManager.move_memory = _patched_move_memory

# Delegate to Serena CLI with start-mcp-server prepended
sys.argv = ["serena", "start-mcp-server"] + sys.argv[1:]

from serena.cli import top_level  # noqa: E402

top_level()
