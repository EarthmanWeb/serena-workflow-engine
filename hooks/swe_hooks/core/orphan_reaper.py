#!/usr/bin/env python3
"""Reap orphaned VS-Code-extension Claude Code sessions.

When VS Code (or Cursor / VS Code Insiders) is restarted or crashes, a Claude
Code session it launched via the plugin's native-binary can survive,
reparented to launchd/init (ppid == 1). Nothing in the UI can reach it (its
stdio parent is gone), but it and its whole descendant tree (Serena, LSPs,
MCP servers) keep running and consuming memory. This module finds and kills
ONLY that exact shape of process:

    - executable path under a `.vscode*` / `.cursor` extensions dir's
      `anthropic.claude-code-*/resources/native-binary/claude`
    - ppid == 1 (no live parent — the defining trait of an orphan)
    - owned by the current user

A terminal `claude` CLI session (parent is a shell) is NEVER matched, even if
its ppid happens to be 1 for some other reason — the executable-path check is
required in addition to ppid==1. The current session's own pid is excluded.

Runs as a SessionStart hook (see hooks/session/swe_session_start.py) and as a
standalone CLI (`python3 orphan_reaper.py --dry-run|--apply`).
"""

import argparse
import os
import re
import signal
import subprocess
import sys
import time


# Matches an executable path ending in:
#   .../<.vscode|.vscode-insiders|.cursor>/extensions/anthropic.claude-code-*/
#     resources/native-binary/claude
_VSCODE_CLAUDE_BINARY_RE = re.compile(
    r"/\.(?:vscode(?:-insiders)?|cursor)/extensions/"
    r"anthropic\.claude-code-[^/]*/resources/native-binary/claude\b"
)


def _parse_ps_line(line):
    """Parse one `ps -axo pid=,ppid=,uid=,command=` line into a dict, or None.

    Fields are whitespace-separated except `command`, which may itself
    contain spaces (args) — so it is captured as everything after the third
    field via a maxsplit split.
    """
    parts = line.strip().split(None, 3)
    if len(parts) < 4:
        return None
    pid_s, ppid_s, uid_s, command = parts
    try:
        pid, ppid, uid = int(pid_s), int(ppid_s), int(uid_s)
    except ValueError:
        return None
    return {"pid": pid, "ppid": ppid, "uid": uid, "command": command}


def find_orphaned_vscode_claude_sessions(ps_output, my_uid, exclude_pids=None):
    """Return the list of process dicts matching the orphan shape.

    ps_output: raw text from `ps -axo pid=,ppid=,uid=,command=`.
    my_uid: current user's numeric uid — only that user's processes match.
    exclude_pids: optional set of pids to never match (e.g. this session's
    own pid and its ancestry).
    """
    exclude_pids = exclude_pids or set()
    matches = []
    for line in (ps_output or "").splitlines():
        proc = _parse_ps_line(line)
        if proc is None:
            continue
        if proc["ppid"] != 1:
            continue
        if proc["uid"] != my_uid:
            continue
        if proc["pid"] in exclude_pids:
            continue
        if not _VSCODE_CLAUDE_BINARY_RE.search(proc["command"]):
            continue
        matches.append(proc)
    return matches


def _default_is_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not signalable by us either way


def kill_matches(matches, kill_fn=None, grace_seconds=3, is_alive_fn=None, sleep_fn=None):
    """SIGTERM every match; escalate to SIGKILL if still alive after grace_seconds.

    Returns the list of pids that were successfully signaled (best-effort —
    a pid that had already exited before we could signal it is not reported
    as reaped). Never raises: a failure to signal one pid never blocks the
    rest.
    """
    kill_fn = kill_fn or os.kill
    is_alive_fn = is_alive_fn or _default_is_alive
    sleep_fn = sleep_fn or time.sleep

    reaped = []
    for m in matches:
        pid = m["pid"]
        try:
            kill_fn(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            continue
        reaped.append(pid)

    if grace_seconds > 0 and reaped:
        sleep_fn(grace_seconds)

    for pid in reaped:
        if not is_alive_fn(pid):
            continue
        try:
            kill_fn(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    return reaped


def _default_ps_output():
    """Fetch `ps -axo pid=,ppid=,uid=,command=` output. POSIX (macOS/Linux)."""
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,uid=,command="],
        capture_output=True, text=True, timeout=5,
    )
    return result.stdout


def reap_orphans(ps_output_fn=None, my_uid=None, kill_fn=None, dry_run=True,
                  grace_seconds=3, exclude_pids=None):
    """Find + (optionally) kill orphaned VS-Code-extension Claude sessions.

    Returns {"matches": [...], "reaped": [...], "error": <str, only on failure>}.
    Never raises — a failure fetching `ps` or matching is reported in the
    result, not propagated, so a caller (e.g. SessionStart) can log a warning
    without ever blocking on it.
    """
    ps_output_fn = ps_output_fn or _default_ps_output
    my_uid = my_uid if my_uid is not None else os.getuid()
    exclude_pids = set(exclude_pids or set())
    exclude_pids.add(os.getpid())

    try:
        ps_output = ps_output_fn()
    except Exception as e:
        return {"matches": [], "reaped": [], "error": str(e)}

    try:
        matches = find_orphaned_vscode_claude_sessions(
            ps_output, my_uid=my_uid, exclude_pids=exclude_pids
        )
    except Exception as e:
        return {"matches": [], "reaped": [], "error": str(e)}

    if dry_run or not matches:
        return {"matches": matches, "reaped": []}

    try:
        reaped = kill_matches(matches, kill_fn=kill_fn, grace_seconds=grace_seconds)
    except Exception as e:
        return {"matches": matches, "reaped": [], "error": str(e)}

    return {"matches": matches, "reaped": reaped}


def _cli():
    parser = argparse.ArgumentParser(
        description="Reap orphaned VS-Code-extension Claude Code sessions "
                     "(ppid==1, native-binary/claude, current user).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="List matches; kill nothing.")
    group.add_argument("--apply", action="store_true", help="SIGTERM (then SIGKILL if needed) matches.")
    parser.add_argument("--grace-seconds", type=int, default=3,
                         help="Seconds to wait after SIGTERM before escalating to SIGKILL (default 3).")
    args = parser.parse_args()

    result = reap_orphans(dry_run=args.dry_run, grace_seconds=args.grace_seconds)

    if "error" in result:
        print(f"orphan_reaper: ERROR: {result['error']}", file=sys.stderr)
        return 1

    if not result["matches"]:
        print("orphan_reaper: no orphaned VS-Code-extension Claude sessions found.")
        return 0

    for m in result["matches"]:
        print(f"pid={m['pid']} ppid={m['ppid']} uid={m['uid']} command={m['command']}")

    if args.dry_run:
        print(f"orphan_reaper: {len(result['matches'])} match(es) — dry run, nothing killed.")
    else:
        print(f"orphan_reaper: reaped {len(result['reaped'])} of {len(result['matches'])} match(es): "
              f"{', '.join(str(p) for p in result['reaped'])}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
