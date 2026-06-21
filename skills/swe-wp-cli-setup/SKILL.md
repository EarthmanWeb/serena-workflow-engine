---
name: swe-wp-cli-setup
version: 1.0.0
description: "Configure the WP-CLI MCP server for a WordPress project. Discovers each site's devcontainer, derives its container name + internal WP path (+ optional SSH), and writes a sectioned .serena/wp-cli.conf. Handles single-project (mono-repo) and multi-repo workspaces. Verifies each site with a read-only WP-CLI call."
workflow:
  aware: true
  callable_from:
    - WF_ONBOARD
    - WF_CLASSIFY
    - WF_EXECUTE
  default_return: WF_CLASSIFY
  supports_standalone: true
---

## ⚠️ WORKFLOW INITIALIZATION

**If starting a new session**, first read workflow initialization:

```
mcp__plugin_swe_serena__read_memory("wf/WF_INIT")
```

Follow WF_INIT instructions before executing this skill.

---

# /swe-wp-cli-setup

Generate (or repair) `<project-root>/.serena/wp-cli.conf` so the `wp_cli` MCP
tool works for this WordPress project.

The conf is the static source of truth read at runtime by the swe plugin's
wp-cli MCP server (`hooks/swe_hooks/mcp/wp_cli_server.py`). This skill is the
ONLY place that writes it — bootstrap delegates here.

## When to run

- After `/swe-init` reports "WordPress + devcontainer detected — run /swe-wp-cli-setup".
- When `wp_cli` fails with `Config error: No WP-CLI config found ...`.
- When sites are added/removed from the workspace.

---

## Conf format (the only format)

One sectioned INI file. A single-project setup is this same format with one
`[site:NAME]` section — there is no separate flat shape.

```ini
# globals
DEFAULT_SITE=<folder-name>     # optional if only one site
PROD_GUARD=true

[site:<folder-name>]
LOCAL_CONTAINER=<slug>-devcontainer-1
LOCAL_PATH=/workspaces/<workspace>/public_html
LOCAL_WORKDIR=/workspaces/<workspace>
REMOTE_SSH=user@host:port/path   # optional; omit for local-only
```

`NAME` is the site's **top-level folder name** — the string the LLM passes as
the `wp_cli` tool's `site` arg.

---

## Stage 1: Determine layout — mono-repo vs multi-repo

Default assumption: **mono-repo** (the project root IS the site). Decide
otherwise only from evidence in the project's own setup/docs (e.g. a CLAUDE.md,
README, or scaffold config describing sibling site repos).

1. Read project docs for layout signals: `CLAUDE.md`, `README.md`, any
   `INDEX_FEATURES` / multi-repo memory.
2. Classify:
   - **Mono-repo** — root has its own `.devcontainer/`. One site.
   - **Multi-repo** — root is a workspace parent (no site `.devcontainer/` of
     its own, or docs say sites are siblings).

Record the decision before discovery.

---

## Stage 2: Discover sites

A **site** = a directory containing a `.devcontainer/` directory (the canonical
marker — do NOT infer sites from folder names or slugs).

- **Mono-repo:** the single site is the project root.
- **Multi-repo:** look for **siblings** of the project root first
  (`<parent>/*/.devcontainer/`). If no sibling sites qualify, fall back to
  **subfolders** of the root (`<root>/*/.devcontainer/`).

Each discovered site is keyed by its **folder name** (basename).

Use `Glob` / `Bash` (`ls -d ../*/.devcontainer` etc.) to enumerate. List the
discovered sites back to the user before writing anything.

---

## Stage 3: Derive per-site values from the devcontainer

For each discovered site, read its own `.devcontainer/` files — never guess:

### 3.1 Container name (`LOCAL_CONTAINER`)

- Read `.devcontainer/.env` for `PROJECT_SLUG` → `<PROJECT_SLUG>-devcontainer-1`.
- Otherwise read `.devcontainer/docker-compose.yml` for the devcontainer
  service's `container_name`, or derive from the compose project name.
- Cross-check against running containers when possible:
  `docker ps --format '{{.Names}}' | grep devcontainer`.

### 3.2 Internal WP path (`LOCAL_PATH`, `LOCAL_WORKDIR`) — CODE IT IN

Determine the **container-internal** WordPress root and write it explicitly into
the conf (do not leave it to runtime resolution):

1. Read `docker-compose.yml` volume mounts to find where the repo mounts inside
   the container (the `/workspaces/<workspace>` target). The workspace is the
   mount whose source is the site repo and which contains `.devcontainer` +
   `public_html`.
2. Read the repo's `wp-cli.yml` `path:` (e.g. `public_html`) to locate WP core
   under that workspace.
3. Compose: `LOCAL_PATH = /workspaces/<workspace>/<wp-cli path>`,
   `LOCAL_WORKDIR = /workspaces/<workspace>`.
4. **Fallback** if undeterminable: standard default
   `LOCAL_PATH = /workspaces/<slug>/public_html`,
   `LOCAL_WORKDIR = /workspaces/<slug>`.

> Note: the workspace dir is identified by the **markers** (`.devcontainer` +
> `public_html` + `wp-cli.yml`), NOT by taking the first `/workspaces/*` entry —
> a container may mount more than one repo.

### 3.3 Remote SSH (`REMOTE_SSH`) — optional

If `.devcontainer/.env` defines remote details (`SSH_USER`, `SSH_HOST`,
`SSH_PORT`, `REMOTE_WP_PATH`), assemble the WP-CLI `--ssh` string:
`[user@]host[:port][path]`. If absent, **omit** `REMOTE_SSH` — the site is
local-only and `target="production"` will fail loudly (correct).

---

## Stage 4: Write `.serena/wp-cli.conf`

- Write globals: `PROD_GUARD=true`, and `DEFAULT_SITE=<name>` where:
  - mono-repo → the single site, OR
  - multi-repo → the root site if the root is itself a site, else the sole
    discovered site, else leave blank (force callers to pass `site`).
- Write one `[site:NAME]` block per discovered site with the derived values.
- **Idempotent:** if the conf exists, reconcile (add missing sites, fix changed
  containers/paths) rather than blindly overwriting. Confirm destructive
  changes with the user.

Use `Write`/`Edit` directly on `.serena/wp-cli.conf` (it is a plain config file,
not a Serena memory).

---

## Stage 5: Verify

For each configured site, run a harmless read-only command through the MCP tool:

```
mcp__plugin_swe_wp-cli__wp_cli(args="option get blogname", site="<name>")
```

- `exit_code == 0` with output → site is wired correctly.
- Container-not-running → report it; the conf is still valid (start the
  container and re-verify).
- Path/`wp-load.php` error → `LOCAL_PATH` is wrong; re-derive in Stage 3.

Report a table of each site and its verification result.

---

## Stage 6: Summary Report

```markdown
## WP-CLI MCP Setup Complete

| Site | Container | LOCAL_PATH | SSH | Verify |
| ---- | --------- | ---------- | --- | ------ |
| ...  | ...       | ...        | y/n | ✅/⚠️  |

- Layout: mono-repo | multi-repo (N sites)
- DEFAULT_SITE: <name | none>
- Conf: .serena/wp-cli.conf (created | reconciled)
```

---

## Skill Return

```markdown
## Skill Return

- **Skill**: swe-wp-cli-setup
- **Status**: success | needs_clarification
- **Sites Configured**: [names]
- **Conf**: .serena/wp-cli.conf
- **Next Step Hint**: WF_CLASSIFY
```

---

## Exit

```
> **Skill /swe-wp-cli-setup complete** — wp_cli MCP configured for [N] site(s)
```

---

## Troubleshooting

### No `.devcontainer/` found anywhere

```
> No WordPress devcontainer found at the project root, its siblings, or its
> subfolders. The wp_cli MCP needs a containerized WP install. Nothing written.
```

Exit with `needs_clarification`.

### `wp_cli` still reports "No WP-CLI config found"

- Confirm the file is at `<project-root>/.serena/wp-cli.conf`.
- The MCP resolves project root from `CLAUDE_PROJECT_DIR` (else cwd) — ensure
  the server is launched with the right project dir.

### Multiple sites, calls hit the wrong one

- Set `DEFAULT_SITE` explicitly, or always pass `site=<folder-name>`.
