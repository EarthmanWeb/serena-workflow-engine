#!/usr/bin/env python3
"""Verify that every `quote` string in doc_rules.json literally appears in
the named memory file. Run from anywhere; paths are resolved relative to
this script's own directory.

Usage:
    python3 verify_doc_quotes.py
Exit code 0 if every quote is found verbatim, 1 otherwise (prints a report
either way).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOC_RULES_PATH = os.path.join(HERE, "doc_rules.json")
MEMORY_ROOT = os.path.join(HERE, "fixture", ".serena", "memory")


def main() -> int:
    with open(DOC_RULES_PATH, encoding="utf-8") as f:
        rules = json.load(f)

    failures = []
    checked = 0
    for rule in rules:
        rule_id = rule.get("id", "?")
        memory_name = rule.get("memory")
        quote = rule.get("quote")
        if not memory_name or not quote:
            failures.append(f"{rule_id}: missing 'memory' or 'quote' field")
            continue
        memory_path = os.path.join(MEMORY_ROOT, memory_name + ".md")
        checked += 1
        if not os.path.exists(memory_path):
            failures.append(f"{rule_id}: memory file not found: {memory_path}")
            continue
        with open(memory_path, encoding="utf-8") as f:
            content = f.read()
        if quote not in content:
            failures.append(
                f"{rule_id}: quote not found verbatim in {memory_name}.md\n"
                f"    quote: {quote!r}"
            )

    print(f"Checked {checked} rule quote(s) against {MEMORY_ROOT}")
    if failures:
        print(f"FAILED: {len(failures)} quote(s) not found verbatim:\n")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("OK: every rule's quote is found verbatim in its named memory file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
