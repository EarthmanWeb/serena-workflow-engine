#!/usr/bin/env python3
"""PostToolUse hook for write_memory — enforce the terse-imperative memory style.

Memories are COMMANDS FOR CLAUDE, not human documentation. The authoritative
style is `ref/REF_MEMORY_STYLE` (shipped as a template so every project inherits
it). This hook fires after every write_memory / edit_memory, reads the memory
that was just written, and flags legacy-style violations so they are rewritten
immediately instead of accumulating.

It is an OBSERVER, never a gate: it always exits 0 and never blocks a write.
Blocking a memory write would deadlock the very init/onboarding flows that create
memories. Enforcement is by loud, specific reminder — the same mechanism as
swe_post_memory_index.py.

Violations detected (all cheap, regex/prefix scans — no semantic analysis):

  1. Missing YAML front-matter block (name/description/metadata.type).
  2. Suggestion-mood guidance ("you should", "consider", "it's a good idea",
     "you may want to", "try to", "it's recommended", "feel free to").
  3. Conversational openers on the first body line ("Let me", "Now ", "In order
     to", "This document/section describes/explains/covers").
  4. Vague quantifiers where a concrete value belongs ("a few", "some amount",
     "small number of", "as appropriate", "if necessary" as a standalone hedge).

WM_* session files are skipped — they are daemon-managed state, not authored
memories, and are exempt from the authored-memory style.
"""

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import output_empty, output_message
    from swe_hooks.core.input import read_stdin_safe, get_input_field
    from swe_hooks.core.session import get_project_root
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PostToolUse")

# Session Working-Memory files are not authored memories — exempt from style.
SKIP_PREFIXES = ("WM_",)

# Memories exempt from the prose scan, matched by basename:
#   REF_MEMORY_STYLE — the authority; it quotes the anti-patterns it forbids.
#   MEMORY — the index; governed by swe_post_memory_index.py, not this hook.
SKIP_BASENAMES = ("REF_MEMORY_STYLE", "MEMORY")

# Suggestion-mood phrases. A rule phrased as a suggestion is treated as optional,
# so these are the highest-value violations to catch. Word-boundary matched,
# case-insensitive.
SUGGESTION_PATTERNS = [
    r"\byou should\b",
    r"\byou may want to\b",
    r"\byou might want to\b",
    r"\bconsider (?:using|adding|doing|whether)\b",
    r"\bit'?s a good idea to\b",
    r"\bit'?s recommended\b",
    r"\bit is recommended\b",
    r"\bwe recommend\b",
    r"\bfeel free to\b",
    r"\btry to\b",
]

# Conversational openers — only flagged at the start of the first body line.
OPENER_PATTERNS = [
    r"^let me\b",
    r"^now[, ]",
    r"^in order to\b",
    r"^this (?:document|section|memory|file) (?:describes|explains|covers|is)\b",
    r"^here'?s\b",
    r"^first,? (?:let'?s|i)\b",
]

# Vague quantifiers where a concrete value fits.
VAGUE_PATTERNS = [
    r"\ba few\b",
    r"\bsome number of\b",
    r"\bsmall number of\b",
    r"\bas appropriate\b",
]

FRONT_MATTER_RE = re.compile(r"^---\s*\n.*?\bmetadata:\s*\n\s*type:\s*\S+", re.DOTALL)


def strip_examples(text):
    """Remove regions where anti-pattern phrases legitimately appear as EXAMPLES,
    so a memory that documents bad style (e.g. ref/REF_MEMORY_STYLE, the audit
    skill) is not flagged for quoting the very phrases it forbids.

    Stripped: fenced code blocks, inline code spans, blockquotes, and Markdown
    table rows (REJECT/CONFORM tables live in table cells). Prose outside these
    regions is what the style rules actually govern.
    """
    # Fenced code blocks (```...``` or ~~~...~~~).
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.DOTALL)
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        # Blockquotes and table rows carry examples/quoted matter — skip them.
        if stripped.startswith(">") or stripped.startswith("|"):
            continue
        # Inline code spans and quoted spans within a prose line carry examples.
        line = re.sub(r"`[^`]*`", " ", line)
        line = re.sub(r"\"[^\"]*\"", " ", line)
        line = re.sub(r"'[^']*'", " ", line)
        kept.append(line)
    return "\n".join(kept)


def find_memory_file(memory_name):
    """Resolve the on-disk path of a just-written memory under .serena/memory/."""
    project_root = get_project_root()
    base = os.path.join(project_root, ".serena", "memory")
    # write_memory accepts topic paths ("feature/FEATURE_X") or bare names.
    rel = memory_name if memory_name.endswith(".md") else f"{memory_name}.md"
    path = os.path.join(base, rel)
    if os.path.isfile(path):
        return path
    return None


def scan_style(content):
    """Return a list of violation strings for the given memory content."""
    violations = []

    # 1. Front-matter block.
    if not FRONT_MATTER_RE.match(content.lstrip("﻿")):
        violations.append(
            "missing front-matter block (--- name / description / metadata.type ---)"
        )

    # Body = content after the front-matter block, for opener detection.
    body = content
    fm_end = content.find("\n---", 3)
    if content.lstrip().startswith("---") and fm_end != -1:
        body = content[fm_end + 4:]

    # Strip example regions (code, quotes, tables) so a memory that DOCUMENTS
    # anti-patterns is judged on its own prose, not the examples it quotes.
    prose = strip_examples(body)
    lowered = prose.lower()

    # 2. Suggestion mood.
    hits = sorted({
        m.group(0).strip()
        for pat in SUGGESTION_PATTERNS
        for m in re.finditer(pat, lowered)
    })
    if hits:
        violations.append(
            f"suggestion-mood phrasing (rewrite as imperative commands): {', '.join(hits)}"
        )

    # 3. Conversational opener on the first non-empty prose line.
    first_line = next(
        (ln.strip() for ln in prose.splitlines()
         if ln.strip() and not ln.strip().startswith("#")),
        "",
    )
    if first_line and any(re.match(p, first_line.lower()) for p in OPENER_PATTERNS):
        violations.append(
            f"conversational opener (lead with the command instead): \"{first_line[:60]}\""
        )

    # 4. Vague quantifiers.
    vhits = sorted({
        m.group(0).strip()
        for pat in VAGUE_PATTERNS
        for m in re.finditer(pat, lowered)
    })
    if vhits:
        violations.append(
            f"vague quantifier (use a concrete value): {', '.join(vhits)}"
        )

    return violations


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        memory_name = get_input_field(input_data, 'tool_input', 'memory_name', default='')
        if not memory_name:
            output_empty()
            return

        basename = memory_name.split("/")[-1]
        if any(memory_name.startswith(p) or basename.startswith(p)
               for p in SKIP_PREFIXES):
            output_empty()
            return
        if basename.removesuffix(".md") in SKIP_BASENAMES:
            output_empty()
            return

        path = find_memory_file(memory_name)
        if not path:
            output_empty()
            return

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        violations = scan_style(content)
        if not violations:
            output_empty()
            return

        lines = "\n".join(f"  - {v}" for v in violations)
        output_message(
            f"✍️ Memory style check — \"{memory_name}\" has legacy-style markers "
            f"(authority: ref/REF_MEMORY_STYLE). Rewrite it now to the terse-"
            f"imperative standard:\n{lines}"
        )
    except Exception:
        output_empty()


if __name__ == "__main__":
    main()
