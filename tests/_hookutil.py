"""Shared test helpers: import SWE hook / core / script modules for testing.

Three loading strategies, one per module shape:

1. `import_hook(rel_path)` — hook scripts under hooks/{post,pre,prompt,stop,session}/.
   Each does a module-top `import swe_hooks.bootstrap` (side-effect-safe: only
   sets sys.path). We add hooks/ and the hook's subdir to sys.path, then import
   by basename.

2. `import_core(dotted)` / `import_module_by_name(dotted)` — packages/modules with
   valid dotted names (e.g. swe_hooks.core.config, swe_hooks.mcp.wm_server). Added
   to sys.path via hooks/, imported normally.

3. `load_script(path)` — files whose names are NOT valid Python identifiers
   (scripts/swe-bootstrap.py, scripts/swe-bypass.py have hyphens) OR whose import
   would run unwanted top-level side effects. Loaded via importlib from an explicit
   file path, so only top-level defs/constants run (the real work sits under
   `if __name__ == "__main__":`).

4. `reset_caches()` — clears the memoized module globals that leak state across
   tests (config._PROJECT_ROOT, state_manager._transition_matrix_cache,
   wm_validator._validator). Call in setUp/tearDown of any test that touches them.

Stdlib only — the SWE plugin ships no third-party test deps.
"""
import importlib
import importlib.util
import os
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS_DIR = os.path.join(PLUGIN_ROOT, "hooks")
SCRIPTS_DIR = os.path.join(PLUGIN_ROOT, "scripts")


def _ensure_hooks_on_path():
    """Put hooks/ on sys.path so `import swe_hooks...` resolves, and set the
    plugin-root env var bootstrap relies on."""
    if HOOKS_DIR not in sys.path:
        sys.path.insert(0, HOOKS_DIR)
    os.environ.setdefault("CLAUDE_PLUGIN_ROOT", PLUGIN_ROOT)


def import_hook(rel_path):
    """Import a hook module by its path relative to hooks/ (no .py extension).

    e.g. import_hook("post/swe_post_memory_index") -> module object.
    """
    _ensure_hooks_on_path()
    subdir = os.path.join(HOOKS_DIR, os.path.dirname(rel_path))
    if subdir not in sys.path:
        sys.path.insert(0, subdir)
    modname = os.path.basename(rel_path)
    return importlib.import_module(modname)


def import_module_by_name(dotted):
    """Import a normally-named module by dotted path (e.g. swe_hooks.core.config)."""
    _ensure_hooks_on_path()
    return importlib.import_module(dotted)


# Convenience alias — core modules are just dotted imports.
import_core = import_module_by_name


def load_script(rel_path, modname=None):
    """Load a script file by its path relative to the plugin root, via importlib.

    Use for files that CANNOT be imported normally:
      - hyphenated filenames (scripts/swe-bootstrap.py) — invalid module identifiers.
    Only top-level defs/constants execute; `if __name__ == "__main__":` blocks do NOT
    run because __name__ is set to the synthetic module name, not "__main__".

    e.g. load_script("scripts/swe-bootstrap.py") -> module object.
    """
    _ensure_hooks_on_path()
    path = os.path.join(PLUGIN_ROOT, rel_path)
    if modname is None:
        base = os.path.basename(rel_path)
        # Sanitize to a valid identifier: swe-bootstrap.py -> _script_swe_bootstrap
        stem = os.path.splitext(base)[0].replace("-", "_")
        modname = "_script_" + stem
    spec = importlib.util.spec_from_file_location(modname, path)
    module = importlib.util.module_from_spec(spec)
    # Register before exec so any self-referential import resolves.
    sys.modules[modname] = module
    spec.loader.exec_module(module)
    return module


def load_serena_patch():
    """Load scripts/serena_memory_patch.py in isolation for testing its pure helpers.

    That module does `from serena.memories.memory_manager import MemoryManager`,
    patches MemoryManager's methods, then `from serena.cli import top_level; top_level()`
    at module top level — importing it normally would start the Serena MCP server.

    We install lightweight stubs for the `serena.*` packages in sys.modules so the
    imports resolve and the method-patching succeeds, and make `top_level` a no-op so
    no server launches. Only the module's own defs/constants then matter — the four
    pure helpers (_derive_prefix, _derive_type, _ensure_front_matter, _normalize_name)
    are what we test.

    Returns the loaded module. Leaves the serena stubs in sys.modules (harmless —
    they only exist to satisfy this one import).
    """
    import types

    def _stub(name):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
        return sys.modules[name]

    _stub("serena")
    _stub("serena.memories")
    mm = _stub("serena.memories.memory_manager")

    class _StubMemoryManager:  # accepts arbitrary method reassignment
        def _find_existing_memory(self, name):
            raise NotImplementedError

        def get_memory_file_path(self, name):
            raise NotImplementedError

        def load_memory(self, name):
            raise NotImplementedError

        def save_memory(self, name, content, is_tool_context=False):
            raise NotImplementedError

        def delete_memory(self, name, is_tool_context=False):
            raise NotImplementedError

        def move_memory(self, old_name, new_name, is_tool_context=False):
            raise NotImplementedError

    mm.MemoryManager = _StubMemoryManager

    cli = _stub("serena.cli")
    cli.top_level = lambda *a, **k: None

    return load_script("scripts/serena_memory_patch.py", modname="_script_serena_memory_patch")


def reset_caches():
    """Clear memoized module globals that otherwise leak state between tests.

    Safe to call even if a module was never imported — it imports lazily and
    resets only what exists.
    """
    _ensure_hooks_on_path()
    try:
        config = importlib.import_module("swe_hooks.core.config")
        config._PROJECT_ROOT = None
    except Exception:
        pass
    try:
        sm = importlib.import_module("swe_hooks.core.state_manager")
        sm._transition_matrix_cache = None
    except Exception:
        pass
    try:
        wmv = importlib.import_module("swe_hooks.core.wm_validator")
        wmv._validator = None
    except Exception:
        pass
