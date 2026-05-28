# SPEC: Cross-Repo Tool Scope for Serena

## Problem

Serena's code intelligence tools (`find_symbol`, `get_symbols_overview`, `find_declaration`, `find_implementations`, `find_referencing_symbols`, `get_diagnostics_for_file`, `replace_symbol_body`, etc.) are hardcoded to the project root directory. In a multi-repo workspace like Convenely (scaffold base + plugin repo + theme repo + admin app + client app), these tools cannot access sibling repos.

**Error observed:**
```
ValueError - '/Users/webdev/LocalSites/convenely/convenely_admin_app' is not in the subpath of
'/Users/webdev/LocalSites/convenely/convenely_scaffold_base'
```

This forces fallback to Claude Code's native tools (Read, Grep, Glob) for cross-repo work, losing Serena's LSP-powered symbol resolution, find-references, rename-symbol, and diagnostics.

## Current State

Three mechanisms exist for cross-repo awareness, but none extends tool scope:

| Mechanism | Config Location | Cross-repo? | What it covers |
|---|---|---|---|
| `memory-paths.conf` | `.serena/memory-paths.conf` | Yes (`:ro` suffix) | Serena memory read/write only |
| `additional_workspace_folders` | `.serena/project.yml` | TypeScript LSP only | Language server symbol discovery |
| Tool path validation | `project.py` (core) | **No** | All tool calls — hardcoded to `project_root` |

### Memory paths (working)

```
# .serena/memory-paths.conf
./.serena/memory
./docs:ro
../convenely_plugin_repo:ro
../convenely_theme_repo:ro
../convenely_admin_app:ro
../convenely_client_app:ro
```

### LSP workspace folders (working for TS only)

```yaml
# .serena/project.yml
additional_workspace_folders:
  - ../convenely_plugin_repo
  - ../convenely_theme_repo
  - ../convenely_admin_app
  - ../convenely_client_app
```

### Tool scope (blocked)

All tool calls go through `Project.validate_relative_path()` → `Project.is_path_in_project()`, which uses `os.path.commonpath()` to enforce that paths are under `project_root`. No configuration exists to extend this.

## Root Cause Analysis

### Where the restriction lives

**File:** `src/serena/project.py` (in Serena core, fork: `EarthmanWeb/serena@swe`)

```python
# Line 620
def is_path_in_project(self, path: str | Path) -> bool:
    if not os.path.isabs(path):
        path = os.path.join(self.project_root, path)
    path = os.path.normpath(path)
    try:
        return os.path.commonpath([self.project_root, path]) == self.project_root
    except ValueError:
        return False

# Line 649
def validate_relative_path(self, relative_path: str, require_not_ignored: bool = False) -> None:
    if not self.is_path_in_project(relative_path):
        raise ValueError(f"{relative_path=} points to path outside of the repository root")
```

### Who calls it

| Caller | File | Purpose |
|---|---|---|
| `read_file` tool | `file_tools.py:38` | Read file contents |
| `write_file` tool | `file_tools.py:71` | Write/create files |
| `list_directory` tool | `file_tools.py:113` | List directory contents |
| `search_for_pattern` tool | `file_tools.py:140` | Regex search in files |
| `replace_content` tool | `file_tools.py:220` | Replace content in files |
| `get_symbol_overview` tool | `symbol_tools.py:95` | `project_root + relative_path` join |
| `find_symbol` tool | `symbol_tools.py:197` → `symbol.py:758` | Symbol search with path filter |

### Symbol tools have a second restriction

`get_symbols_overview` in `symbol_tools.py` (line 95) does:
```python
file_path = os.path.join(self.project.project_root, relative_path)
```
This means even if `is_path_in_project` were extended, symbol tools would still resolve paths relative to `project_root`.

### LSP already knows about workspace folders

The `additional_workspace_folders` config is passed to `LanguageServerManager` which registers them as LSP workspace folders. The language servers (TypeScript, PHP) **can** discover symbols in these folders. The restriction is purely in Serena's Python tool layer, not in the underlying language servers.

## Proposed Solution

### Option A: Extend `is_path_in_project` to include workspace folders (Minimal)

Modify `Project.is_path_in_project()` to also accept paths under `additional_workspace_folders`:

```python
def is_path_in_project(self, path: str | Path) -> bool:
    if not os.path.isabs(path):
        path = os.path.join(self.project_root, path)
    path = os.path.normpath(path)

    # Check primary project root
    try:
        if os.path.commonpath([self.project_root, path]) == self.project_root:
            return True
    except ValueError:
        pass

    # Check additional workspace folders
    for ws_folder in self._resolved_workspace_folders:
        try:
            if os.path.commonpath([ws_folder, path]) == ws_folder:
                return True
        except ValueError:
            continue

    return False
```

**Pros:** Minimal change, reuses existing config.
**Cons:** Doesn't address `project_root + relative_path` joins in symbol tools. Workspace folders would need to be addressable by a prefix (e.g., `@admin_app/src/App.tsx`).

### Option B: Add `tool_scope_paths` config (Explicit)

New `project.yml` config that explicitly extends tool scope:

```yaml
# Paths accessible to code intelligence tools (read-only by default)
tool_scope_paths:
  - path: ../convenely_plugin_repo
    read_only: true
  - path: ../convenely_theme_repo
    read_only: true
  - path: ../convenely_admin_app
    read_only: false
  - path: ../convenely_client_app
    read_only: false
```

**Changes required:**
1. `project.py` — parse `tool_scope_paths`, resolve to absolute, store as `_tool_scope_dirs`
2. `project.py:is_path_in_project()` — check `_tool_scope_dirs` in addition to `project_root`
3. `project.py:validate_relative_path()` — handle paths that are relative to a scope dir, not project root
4. `symbol_tools.py` — resolve `relative_path` against the correct scope root
5. `file_tools.py` — enforce `read_only` for scope dirs marked as such

**Pros:** Explicit, separates tool scope from LSP workspace config, supports read-only enforcement.
**Cons:** More config, more code, new concept to document.

### Option C: Reuse `additional_workspace_folders` for tool scope (Pragmatic)

Extend the existing `additional_workspace_folders` to also grant tool access:

```yaml
additional_workspace_folders:
  - path: ../convenely_plugin_repo
    tools: true        # enable tool access (default: false for backward compat)
    read_only: true    # tool writes blocked
  - ../convenely_theme_repo    # backward-compat: string = LSP only, no tools
```

**Changes required:** Same as Option B but reuses existing config key.

**Pros:** No new config concept, backward compatible (string entries = LSP only).
**Cons:** Overloads the meaning of `additional_workspace_folders`.

## Recommendation

**Option A** as immediate fix — it's a 10-line patch to the fork (`EarthmanWeb/serena@swe`) and unlocks the most common use case: `find_symbol` without a `relative_path` filter (global search across all workspace folders).

**Option B** as the proper solution — should be proposed upstream to Serena or implemented in the fork with clear semantics.

### Immediate workaround (no code change)

Symlink sibling repos into the project root:

```bash
cd convenely_scaffold_base
ln -s ../convenely_plugin_repo .plugin_repo
ln -s ../convenely_admin_app .admin_app
```

Then use `.plugin_repo/em-app-bridge/...` as relative paths. Serena already allows symlinks explicitly:

> "we intentionally allow symlinks, as the assumption is that they point to relevant project files"

**Downside:** Pollutes project root, requires `.gitignore` entries, fragile.

## Files to Modify (for Option A)

| File | Change |
|---|---|
| `src/serena/project.py` | `is_path_in_project()` — check workspace folders |
| `src/serena/project.py` | `__init__` or config loading — resolve workspace folder abs paths |
| `src/serena/tools/symbol_tools.py` | `get_symbol_overview()` — resolve path against correct root |

## Open Questions

1. Should workspace folder paths be addressable as `@folder_name/path` or `../folder/path`?
2. Should editing tools (`replace_content`, `write_file`) work in workspace folders or only read tools?
3. Should this be upstreamed to Serena or kept in the `@swe` fork?
4. Does the `--project` CLI flag need to support multiple roots?
