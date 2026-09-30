"""Memory-size measurement and advisory thresholds.

Sizes are UTF-8 DECODED CHARACTER COUNTS of the WHOLE memory file, including
its YAML front-matter block. UNREADABLE_CHARS = 50,000 is MEASURED, not
provisional: a 50,052-char memory (front-matter stripped by Serena) was
delivered inline; 53,734- and 64,345-char memories were replaced by Claude
Code's `<persisted-output> Output too large … Preview (first 2KB)` block
(see GitHub anthropics/claude-code#97622). No large-output warning appeared
below the cutoff at any size tested.
"""

import os
import re

# Budget thresholds, in UTF-8 decoded characters of the whole file (incl.
# front-matter). See module docstring for the source of each number.
WARN_CHARS = 8000
SPLIT_CHARS = 16000
UNREADABLE_CHARS = 50000

CONF_PATH = os.path.join(".serena", "memory-paths.conf")

# Topic segments excluded from size measurement/advisories everywhere.
EXCLUDED_TOPICS = ("spec", "report", "research", "project")

# Basename prefixes for excluded topics, derived from EXCLUDED_TOPICS (e.g.
# "spec" -> "SPEC_"). Covers a bare "SPEC_Z" with no topic directory.
_EXCLUDED_BASENAME_PREFIXES = tuple(f"{t.upper()}_" for t in EXCLUDED_TOPICS)


def is_excluded_memory(name: str) -> bool:
    """True when `name` belongs to an excluded topic (spec/, report/,
    research/, project/).

    `name` is a memory name as produced by the audit/validator tools:
    an optional alias prefix, then path segments, then a basename, e.g.
    "spec/SPEC_X", "em/spec/SPEC_X", "report/REPORT_Y", "research/RESEARCH_Z",
    "project/PROJECT_Q", "dom/DOM_SPECIAL", "ref/REF_SPEC_PARSER", or a bare
    "SPEC_Z" with no topic segment at all.

    True when ANY path segment other than the basename equals an excluded
    topic (case-insensitive), OR the basename itself starts with one of the
    excluded-topic prefixes ("SPEC_", "REPORT_", "RESEARCH_", "PROJECT_",
    case-insensitive) — covering a bare "SPEC_Z" with no topic directory.
    """
    if not name:
        return False
    parts = name.split("/")
    basename = parts[-1]
    dirs = parts[:-1]
    for seg in dirs:
        if seg.lower() in EXCLUDED_TOPICS:
            return True
    basename_upper = basename.upper()
    if basename_upper.startswith(_EXCLUDED_BASENAME_PREFIXES):
        return True
    return False


def parse_root_arg(raw):
    """Parse a --root value ([alias=]DIR) into (alias_or_None, dir)."""
    if "=" in raw:
        alias, _, path = raw.partition("=")
        alias = alias.strip()
        path = path.strip()
        if alias:
            return alias, path
    return None, raw.strip()


def load_conf_roots(conf_path):
    """Parse a memory-paths.conf file into a list of (alias_or_None, dir).

    Entry syntax: [alias=]path[:ro], one per line. '#' comments and blank
    lines ignored. Relative paths resolve against the CURRENT WORKING
    DIRECTORY (not the conf file's location). A trailing ':ro' marker is
    stripped (read-only roots are still scanned, just not written to).
    """
    roots = []
    try:
        with open(conf_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return roots

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith(":ro"):
            line = line[: -len(":ro")]
        line = line.strip()
        if not line:
            continue
        alias, path = parse_root_arg(line)
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), path)
        roots.append((alias, os.path.normpath(path)))
    return roots


def resolve_roots(cli_roots, conf_path=CONF_PATH):
    """Resolve the final (alias_or_None, dir) list from --root args or conf.

    `cli_roots` — raw --root strings (each optionally "alias=DIR"), or falsy.
    Returns None when no --root args are given and no conf file resolves any
    roots — callers should treat that as a usage error.
    """
    if cli_roots:
        resolved = []
        for raw in cli_roots:
            alias, path = parse_root_arg(raw)
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            resolved.append((alias, os.path.normpath(path)))
        return resolved

    if os.path.isfile(conf_path):
        roots = load_conf_roots(conf_path)
        if roots:
            return roots

    return None

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.*?)(?:\s+#+)?\s*\r?$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

PREAMBLE_HEADING = "(preamble)"


def measure_memory(text):
    """Measure a memory file's raw text.

    Returns a dict:
      chars       — len(text) (UTF-8 decoded character count)
      bytes       — len(text.encode("utf-8"))
      words       — len(text.split())
      tokens_est  — chars // 4 (rough token estimate)
      sections    — list of {"heading", "level", "chars"} for every ##/###/####
                    heading line, in document order. Content from a heading
                    line up to (but not including) the next heading of ANY
                    level belongs to that heading's char count. Content before
                    the first heading is counted under the synthetic heading
                    "(preamble)" (level 0) — omitted if empty.
                    Heading lines inside fenced code blocks (``` or ~~~) are
                    ignored (not treated as section boundaries).
    """
    text = text or ""
    chars = len(text)
    encoded_bytes = len(text.encode("utf-8"))
    words = len(text.split())
    tokens_est = chars // 4

    lines = text.splitlines(keepends=True)

    # sections_raw: list of (heading_text_or_None, level, start_char_offset)
    sections_raw = []
    in_fence = False
    offset = 0
    for line in lines:
        stripped_for_fence = line.rstrip("\n")
        if _FENCE_RE.match(stripped_for_fence):
            in_fence = not in_fence
            offset += len(line)
            continue
        if not in_fence:
            m = _HEADING_RE.match(stripped_for_fence)
            if m:
                level = len(m.group(1))
                heading = m.group(2).strip()
                sections_raw.append((heading, level, offset))
        offset += len(line)

    sections = []
    if not sections_raw or sections_raw[0][2] > 0:
        preamble_end = sections_raw[0][2] if sections_raw else chars
        preamble_text_chars = preamble_end
        if preamble_text_chars > 0:
            sections.append({
                "heading": PREAMBLE_HEADING,
                "level": 0,
                "chars": preamble_text_chars,
            })

    for i, (heading, level, start) in enumerate(sections_raw):
        end = sections_raw[i + 1][2] if i + 1 < len(sections_raw) else chars
        sections.append({
            "heading": heading,
            "level": level,
            "chars": end - start,
        })

    return {
        "chars": chars,
        "bytes": encoded_bytes,
        "words": words,
        "tokens_est": tokens_est,
        "sections": sections,
    }


def classify_size(chars, warn=WARN_CHARS, split=SPLIT_CHARS, unreadable=UNREADABLE_CHARS):
    """Classify a char count against the budget thresholds.

    Returns one of "ok" | "warn" | "split" | "unreadable":
      ok:         chars <= warn
      warn:       warn  <  chars <= split
      split:      split <  chars <  unreadable
      unreadable: chars >= unreadable
    """
    if chars >= unreadable:
        return "unreadable"
    if chars <= warn:
        return "ok"
    if chars <= split:
        return "warn"
    return "split"


def size_advisory(name, text):
    """Return a one-line advisory string for a memory, or None when ok.

    None is returned when classify_size(len(text)) == "ok", OR when `name`
    is an excluded memory (spec/, report/, research/, project/ — see
    is_excluded_memory). Otherwise a single line naming the memory, its
    size, and the budget, pointing at /swe-memory-size-audit.
    """
    if is_excluded_memory(name):
        return None
    chars = len(text or "")
    status = classify_size(chars)
    if status == "ok":
        return None

    tokens = chars // 4
    return (
        f"\U0001F4CF MEMORY SIZE: {name} is {chars:,} chars (~{tokens:,} tokens) "
        f"— {status.upper()} (budget: ≤{WARN_CHARS:,} target, "
        f">{SPLIT_CHARS:,} must split, ≥{UNREADABLE_CHARS:,} unreadable: "
        f"Claude Code replaces the read with a 2KB preview). "
        f"Run /swe-memory-size-audit to split it into a hub + focused children."
    )
