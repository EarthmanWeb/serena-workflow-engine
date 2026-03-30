#!/usr/bin/env python3
"""Wrapper that patches Serena's memory name resolution before starting.

Adds automatic directory-prefix resolution for memory names:
  SYS_BUILDER_WYSIWYG  ->  sys/SYS_BUILDER_WYSIWYG
  DOM_BUILDER_BLOCKS   ->  dom/DOM_BUILDER_BLOCKS
  FEATURE_SWE          ->  feature/FEATURE_SWE

The prefix is derived from the first segment before '_', lowercased.
Falls back to flat file lookup if prefix directory doesn't contain the file.
"""

import sys

from serena.project import MemoriesManager

_original_find_memory = MemoriesManager._find_memory


def _patched_find_memory(self, name):
    # Try the name as-is first (handles both prefixed and flat names)
    result = _original_find_memory(self, name)
    if result is not None:
        return result

    # Auto-resolve: derive directory prefix from memory name convention
    # e.g. SYS_BUILDER_WYSIWYG -> sys/SYS_BUILDER_WYSIWYG
    clean = name.replace(".md", "")
    if "/" not in clean and "_" in clean:
        prefix = clean.split("_")[0].lower()
        if prefix:  # skip names starting with _ (e.g. _INDEX)
            result = _original_find_memory(self, f"{prefix}/{clean}")
            if result is not None:
                return result

    return None


MemoriesManager._find_memory = _patched_find_memory

# Delegate to Serena CLI with start-mcp-server prepended
sys.argv = ["serena", "start-mcp-server"] + sys.argv[1:]

from serena.cli import top_level  # noqa: E402

top_level()
