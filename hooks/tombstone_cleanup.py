"""One-time cleanup of this plugin's own old cached versions (retired plugin)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = ".tombstone-cleaned"
PURGED = "tombstone-purged"
NOTIFIED = ".tombstone-notified"
NOTICE = (
    "The SWE plugin has moved to a new private marketplace "
    "(EarthmanWeb/claude-workflow-engine). Ask the maintainer for access, "
    "then remove this copy: claude plugin uninstall swe@EarthmanWeb"
)
PLUGIN_NAME = "swe"
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def is_own_cache_root(path: Path) -> bool:
    """True only for <...>/plugins/cache/<marketplace>/swe/<X.Y.Z>."""
    p = Path(path)
    if not SEMVER.match(p.name):
        return False
    plugin_dir = p.parent
    if plugin_dir.name != PLUGIN_NAME:
        return False
    marketplace_dir = plugin_dir.parent
    if not marketplace_dir.name:
        return False
    cache_dir = marketplace_dir.parent
    if cache_dir.name != "cache" or cache_dir.parent.name != "plugins":
        return False
    return p.is_dir()


def siblings_to_remove(root: Path) -> list[Path]:
    """Every entry under .../swe/ except root."""
    root = Path(root)
    return sorted(c for c in root.parent.iterdir() if c.name != root.name)


def cleanup(root: Path) -> list[Path]:
    """Remove sibling version dirs once; write marker after. Returns removed."""
    root = Path(root)
    marker = root / MARKER
    if marker.exists():
        return []
    removed: list[Path] = []
    for sib in siblings_to_remove(root):
        if sib.is_symlink():
            sib.unlink()
        elif sib.is_dir():
            shutil.rmtree(sib)
        else:
            sib.unlink()
        removed.append(sib)
    marker.write_text("done\n")
    return removed


def _git(repo: Path, *args: str, timeout: int = 40) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=timeout)


def marketplace_dir(root: Path) -> Path | None:
    """The marketplace clone that served this cache root (registry first)."""
    root = Path(root)
    plugins = root.parents[3]
    name = root.parents[1].name
    try:
        reg = json.loads((plugins / "known_marketplaces.json").read_text())
        loc = reg.get(name, {}).get("installLocation")
        if loc:
            return Path(loc)
    except (OSError, ValueError, AttributeError):
        pass
    return plugins / "marketplaces" / name


def is_tombstone_clone(repo: Path) -> bool:
    """True only when the clone's HEAD is a parentless commit carrying this
    retired plugin's manifest (name swe, major version 99)."""
    if not (Path(repo) / ".git").is_dir():
        return False
    parents = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD")
    if parents.returncode != 0 or len(parents.stdout.split()) != 1:
        return False
    shown = _git(repo, "show", "HEAD:.claude-plugin/plugin.json")
    if shown.returncode != 0:
        return False
    try:
        manifest = json.loads(shown.stdout)
    except ValueError:
        return False
    version = str(manifest.get("version", ""))
    return manifest.get("name") == PLUGIN_NAME and version.split(".")[0] == "99"


def purge_marketplace_history(root: Path) -> bool:
    """Drop every pre-tombstone object from the marketplace clone, keeping .git
    so later marketplace updates (fetch + reset --hard) keep working."""
    repo = marketplace_dir(root)
    if repo is None or not repo.is_dir() or (repo / ".git" / PURGED).exists():
        return False
    if not is_tombstone_clone(repo):
        return False
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    branch = _git(repo, "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    refs = _git(repo, "for-each-ref", "--format=%(refname) %(objectname)").stdout.splitlines()
    keep = {f"refs/heads/{branch}", f"refs/remotes/origin/{branch}", "refs/remotes/origin/HEAD"}
    for line in refs:
        ref, _, sha = line.partition(" ")
        if ref not in keep or sha != head:
            _git(repo, "update-ref", "-d", ref)
    git_dir = repo / ".git"
    for name in ("ORIG_HEAD", "FETCH_HEAD", "shallow", "packed-refs.lock"):
        (git_dir / name).unlink(missing_ok=True)
    shutil.rmtree(git_dir / "logs", ignore_errors=True)
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "--prune=now", "--quiet")
    total = _git(repo, "cat-file", "--batch-all-objects", "--batch-check").stdout.splitlines()
    reachable = _git(repo, "rev-list", "--objects", "--all").stdout.splitlines()
    if len(total) != len(reachable):
        return False
    (git_dir / PURGED).write_text("done\n")
    return True


def main() -> int:
    try:
        raw = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
        if not raw:
            return 0
        root = Path(raw)
        if not is_own_cache_root(root):
            return 0
        try:
            purge_marketplace_history(root)
        except Exception:
            pass
        cleanup(root)
        flag = root / NOTIFIED
        if not flag.exists():
            flag.write_text("done\n")
            print(json.dumps({"systemMessage": NOTICE}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
