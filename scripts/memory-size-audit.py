#!/usr/bin/env python3
"""Audit Serena memory files against the size/readability budget.

Flags memories that are large enough to risk Claude Code's MCP text-result
disk-persistence cutoff (large reads truncate to a 2KB preview) or that are
simply too big for a single focused read. See
hooks/swe_hooks/core/memory_size.py for the threshold rationale.

Roots:
  --root [alias=]DIR   Repeatable. A memory root directory.
                        Aliased roots (alias=DIR) produce memory names
                        prefixed "<alias>/".

  Without any --root, reads `.serena/memory-paths.conf` from the CURRENT
  WORKING DIRECTORY. Each non-blank, non-comment line is
  `[alias=]path[:ro]`; relative paths resolve against the cwd; a trailing
  `:ro` marker is stripped. No --root AND no conf file is an error (exit 2)
  — there is no silent fallback to a hardcoded default.

  Every resolved root (from --root or from the conf file) MUST exist as a
  directory. A root that does not exist (typo'd --root, or a stale conf
  entry) is a fatal error, not a silent skip: one "ERROR: memory root not
  found: <alias=>path" line is printed to stderr per missing root and the
  script exits 2 without scanning anything.

Memory names are the file's path relative to its root, without the `.md`
extension, prefixed `<alias>/` for an aliased root. WM_*.md files (session
working-memory, not authored memories) are always skipped.

Usage:
  python3 scripts/memory-size-audit.py --root memories
  python3 scripts/memory-size-audit.py --root em=../em-serena/.serena/memory
  python3 scripts/memory-size-audit.py                      # uses .serena/memory-paths.conf
  python3 scripts/memory-size-audit.py --topic dom/ --topic ref/
  python3 scripts/memory-size-audit.py --json
  python3 scripts/memory-size-audit.py --all --sections 3
  python3 scripts/memory-size-audit.py --warn 6000 --split 12000 --unreadable 30000

Exit code: 1 if any memory is "split" or "unreadable", 0 otherwise (2 for a
usage/config error — no roots resolvable, or a resolved root does not
exist).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks"))
from swe_hooks.core.memory_size import (  # noqa: E402
    WARN_CHARS,
    SPLIT_CHARS,
    UNREADABLE_CHARS,
    CONF_PATH,
    measure_memory,
    classify_size,
    parse_root_arg,
    load_conf_roots,
    resolve_roots,
)


def find_memory_files(root_dir):
    """Yield relative POSIX-style paths (no .md) for every memory file under root_dir.

    Skips WM_*.md files.
    """
    for dirpath, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if not fname.endswith(".md"):
                continue
            if fname.startswith("WM_"):
                continue
            abspath = os.path.join(dirpath, fname)
            rel = os.path.relpath(abspath, root_dir)
            rel = rel.replace(os.sep, "/")
            yield rel[:-3], abspath


def collect_memories(roots, topics, warn, split, unreadable, sections_n):
    """Walk every root, measure every memory, return a sorted list of records.

    A root directory that does not exist is a fatal error (fail fast, no
    silent skip): every missing root is printed to stderr and the caller
    must treat this as an exit-2 condition (see main()).
    """
    records = []
    missing = []
    for alias, root_dir in roots:
        if not os.path.isdir(root_dir):
            label = f"{alias}={root_dir}" if alias else root_dir
            missing.append(label)
            continue
        for rel, abspath in find_memory_files(root_dir):
            name = f"{alias}/{rel}" if alias else rel
            if topics and not any(name.startswith(t) for t in topics):
                continue
            try:
                with open(abspath, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                text = ""
                read_error = str(e)
            else:
                read_error = None

            measured = measure_memory(text)
            status = classify_size(measured["chars"], warn=warn, split=split, unreadable=unreadable)
            top_sections = sorted(
                measured["sections"], key=lambda s: s["chars"], reverse=True
            )[:sections_n]

            record = {
                "name": name,
                "path": abspath,
                "chars": measured["chars"],
                "bytes": measured["bytes"],
                "words": measured["words"],
                "tokens_est": measured["tokens_est"],
                "status": status,
                "sections": top_sections,
            }
            if read_error:
                record["error"] = read_error
            records.append(record)

    if missing:
        for label in missing:
            print(f"ERROR: memory root not found: {label}", file=sys.stderr)
        return None

    records.sort(key=lambda r: r["chars"], reverse=True)
    return records


def main():
    parser = argparse.ArgumentParser(
        description="Audit Serena memory files against the size/readability budget.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--root", action="append", dest="roots", default=None,
        help="Memory root directory, optionally '[alias=]DIR' (repeatable).",
    )
    parser.add_argument(
        "--topic", action="append", dest="topics", default=None,
        help="Only include memories whose name starts with this prefix (repeatable).",
    )
    parser.add_argument("--warn", type=int, default=WARN_CHARS, help="Warn threshold (chars).")
    parser.add_argument("--split", type=int, default=SPLIT_CHARS, help="Split threshold (chars).")
    parser.add_argument(
        "--unreadable", type=int, default=UNREADABLE_CHARS, help="Unreadable threshold (chars)."
    )
    parser.add_argument(
        "--sections", type=int, default=5,
        help="Show the N largest sections under each flagged memory (default 5).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a text table.")
    parser.add_argument(
        "--all", action="store_true",
        help="Text output: include 'ok' memories too (default: only non-ok rows).",
    )
    args = parser.parse_args()

    roots = resolve_roots(args.roots)
    if roots is None:
        print(
            "error: no --root given and no .serena/memory-paths.conf found in the "
            "current working directory. Pass --root DIR at least once, or run from "
            "a project with .serena/memory-paths.conf.",
            file=sys.stderr,
        )
        return 2

    records = collect_memories(
        roots, args.topics, args.warn, args.split, args.unreadable, args.sections
    )
    if records is None:
        # collect_memories already printed one "ERROR: memory root not
        # found: ..." line per missing root to stderr.
        return 2

    counts = {"ok": 0, "warn": 0, "split": 0, "unreadable": 0}
    for r in records:
        counts[r["status"]] += 1

    if args.json:
        out = {
            "thresholds": {"warn": args.warn, "split": args.split, "unreadable": args.unreadable},
            "memories": records,
            "counts": counts,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        rows = records if args.all else [r for r in records if r["status"] != "ok"]
        header = f"{'STATUS':<11} {'CHARS':>8} {'~TOKENS':>8}  NAME"
        print(header)
        print("-" * len(header))
        for r in rows:
            print(f"{r['status'].upper():<11} {r['chars']:>8,} {r['tokens_est']:>8,}  {r['name']}")
            if r["status"] != "ok":
                for s in r["sections"]:
                    heading = s["heading"] or "(untitled)"
                    print(f"    {'':<11} {s['chars']:>8,} {'':>8}    {heading}")
        print()
        print(
            f"counts: ok={counts['ok']} warn={counts['warn']} "
            f"split={counts['split']} unreadable={counts['unreadable']}"
        )

    return 1 if (counts["split"] or counts["unreadable"]) else 0


if __name__ == "__main__":
    sys.exit(main())
