"""Shared test helper: import a SWE hook script as a module.

Hooks live in hooks/{post,pre,prompt,stop,session}/ and each does a module-top
`import swe_hooks.bootstrap` which only sets up sys.path (side-effect-safe). To
import a hook in a test we add both `hooks/` and the hook's own subdir to
sys.path, then import by basename.

Stdlib only — the SWE plugin ships no third-party test deps.
"""
import importlib
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(PLUGIN_ROOT, "hooks")


def import_hook(rel_path):
    """Import a hook module by its path relative to hooks/ (no .py extension).

    e.g. import_hook("post/swe_post_memory_index") -> module object.
    """
    subdir = os.path.join(HOOKS_DIR, os.path.dirname(rel_path))
    for p in (HOOKS_DIR, subdir):
        if p not in sys.path:
            sys.path.insert(0, p)
    # Ensure CLAUDE_PLUGIN_ROOT is set so bootstrap resolves the right hooks dir.
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", PLUGIN_ROOT)
    modname = os.path.basename(rel_path)
    return importlib.import_module(modname)
