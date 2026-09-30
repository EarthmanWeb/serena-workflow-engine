#!/usr/bin/env python3
"""PreToolUse hook — HARD-DENY non-indexed category links entering MEMORY.md.

MEMORY.md is the auto-loaded session index. spec/report/research/project
memories are browsed via list_memories(topic=...) and are NEVER indexed there —
an indexed spec rides into every session's context and gets read as general
feature knowledge (the exact leak this gate closes).

swe_post_memory_index.py already states the rule but is PostToolUse-advisory:
it cannot deny, and it only fires on write_memory — index edits made via
edit_memory or raw Edit/Write slipped through. This gate runs BEFORE the write
and denies it, state-independently.

Matches: write_memory / edit_memory (Serena, both server prefixes) + Edit/Write.
Fires ONLY when the target is the MEMORY index AND the written content
introduces a link into a non-indexed category. Everything else passes silently.

SECOND DUTY (B4) — new-memory dedupe: a write_memory that CREATES a memory
(name not on disk under .serena/memory/**, .serena/memories/** or memories/**)
is denied when an existing memory already covers its topic — the dumb check:
every distinctive (>= 4 char) token of the new name (dir + REF_/SPEC_/DOM_/
FEATURE_/SYS_ prefixes stripped) appears in one existing memory's basename or
body. The remedy is edit_memory on the hit, not a near-duplicate file; the
literal tag [new-memory-justified: <reason>] in the content overrides. Edits/
overwrites of EXISTING memories and WM_ session files always pass.

THIRD DUTY (Change Set H) — obligations-digest enforcement: a write_memory (or
direct Write of a *.md under a /.serena/memory/ path) that CREATES or
OVERWRITES a memory under a rule-bearing prefix (dom/, ref/, dev/, feature/)
is denied when the content's front-matter carries no `obligations:` field.
`obligations: []` is the conscious-none escape and always passes. edit_memory
(partial edits) and non-rule-bearing prefixes are never denied by this check.
The digest this field captures is what the two-tier sweep (wm_server
_check_memory_sweep) plans obligations from without a full body read.

FOURTH DUTY — site-data denial: a memory write carrying detectable
site-specific infrastructure data (real IPv4 addresses, real email addresses,
credentialed URLs, SSH connect strings to real hosts, private-key blocks, or
cloud/API token prefixes) is HARD-DENIED, no override. This closes the leak
where /swe-feature-onboard wrote a site's real infrastructure details into a
project's committed memories. Applies to the same tool matches as the other
duties: write_memory/edit_memory (both server prefixes, content/repl fields)
and direct Edit/Write of a *.md under a /.serena/memory/ tree (new_string/
content fields). A documentation-range placeholder (loopback, RFC 5737 test
nets, example.com/.test/.invalid/.localhost/.local domains, angle-bracket
`<token>` URL userinfo, `noreply@anthropic.com`, `git@github.com:<org>/<repo>`
placeholders) never denies. See `mem:ref/REF_NO_SITE_DATA`.
"""

import os
import re
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import swe_hooks.bootstrap  # noqa: E402

try:
    from swe_hooks.core.output import HookOutput, output_empty
    from swe_hooks.core.input import read_stdin_safe
except ImportError as e:
    swe_hooks.bootstrap.import_error_exit(e, "PreToolUse")

# Categories that must never appear as MEMORY.md index links. Keep in sync with
# NON_INDEXED_CATEGORIES in hooks/post/swe_post_memory_index.py.
NON_INDEXED_CATEGORIES = ("spec", "report", "research", "project")

# Markdown link whose target is inside a non-indexed topic dir, e.g.
# "](spec/SPEC_X.md)" or "](.serena/memory/report/REPORT_Y.md)".
_CATEGORY_DIR_LINK = re.compile(
    r"\]\(\s*[^)]*\b(?:%s)/" % "|".join(NON_INDEXED_CATEGORIES), re.IGNORECASE
)
# Markdown link to a category file by bare basename, e.g. "](SPEC_X.md)".
_CATEGORY_FILE_LINK = re.compile(
    r"\]\(\s*[^)/]*\b(?:SPEC|REPORT|RESEARCH|PROJECT)_[^)]*\.md\s*\)"
)

# Content-bearing fields across the matched tools:
#   write_memory: content · edit_memory: repl · Edit: new_string · Write: content
CONTENT_FIELDS = ("content", "repl", "new_string")

# ---------------------------------------------------------------------------
# B4 — new-memory dedupe
# ---------------------------------------------------------------------------
# Memory trees scanned for existing memories, relative to the session cwd.
MEMORY_DIR_NAMES = (".serena/memory", ".serena/memories", "memories")

# Type prefixes stripped off a basename before topic tokenization.
MEMORY_TYPE_PREFIXES = ("REF_", "SPEC_", "DOM_", "FEATURE_", "SYS_")

# Literal override tag: a deliberate, justified new memory passes the gate.
NEW_MEMORY_OVERRIDE_RE = re.compile(r"\[new-memory-justified:\s*[^\]]+\]")

# A topic token must be at least this long to count as distinctive.
_DISTINCTIVE_TOKEN_LEN = 4

# Body-scan cap per existing memory (bytes) — the scan stays cheap.
_BODY_SCAN_CAP = 65536

_TOKEN_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")


def _strip_type_prefix(basename):
    """Strip one leading REF_/SPEC_/DOM_/FEATURE_/SYS_ type prefix."""
    for prefix in MEMORY_TYPE_PREFIXES:
        if basename.upper().startswith(prefix):
            return basename[len(prefix):]
    return basename


def memory_topic_tokens(memory_name):
    """Distinctive topic tokens of a memory name: basename only (dir prefix
    dropped), type prefix stripped, split on non-alphanumerics, lowercase,
    tokens shorter than 4 chars discarded."""
    base = str(memory_name).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    if base.endswith(".md"):
        base = base[:-3]
    base = _strip_type_prefix(base)
    return {t for t in _TOKEN_SPLIT_RE.split(base.lower())
            if len(t) >= _DISTINCTIVE_TOKEN_LEN}


def _existing_memory_files(cwd):
    """Yield (tree_root, file_path) for every .md under the memory trees."""
    for rel_dir in MEMORY_DIR_NAMES:
        root = os.path.join(cwd, rel_dir)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fname in filenames:
                if fname.endswith(".md"):
                    yield root, os.path.join(dirpath, fname)


def memory_exists(cwd, memory_name):
    """True when memory_name already exists on disk in any memory tree —
    by its exact relative path or by basename anywhere in a tree."""
    name = str(memory_name).replace("\\", "/").strip().strip("/")
    if name.endswith(".md"):
        name = name[:-3]
    target_base = name.rsplit("/", 1)[-1] + ".md"
    for root, path in _existing_memory_files(cwd):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel == name + ".md" or os.path.basename(path) == target_base:
            return True
    return False


def find_on_topic_memories(cwd, tokens, limit=5):
    """Existing memories that cover EVERY token — in their basename tokens or
    (cheap python scan, capped) their body. Returns tree-relative names
    without '.md'. MEMORY.md and WM_ session files never count as hits."""
    hits = []
    for root, path in _existing_memory_files(cwd):
        base = os.path.basename(path)
        if base == "MEMORY.md" or base.startswith("WM_"):
            continue
        base_tokens = memory_topic_tokens(base)
        uncovered = [t for t in tokens if t not in base_tokens]
        if uncovered:
            try:
                with open(path, "r", errors="replace") as f:
                    body = f.read(_BODY_SCAN_CAP).lower()
            except OSError:
                continue
            if any(t not in body for t in uncovered):
                continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        hits.append(rel[:-3] if rel.endswith(".md") else rel)
        if len(hits) >= limit:
            break
    return hits


def new_memory_dedupe_denial(tool_name, tool_input, cwd):
    """B4 verdict: the deny message, or None to allow.

    Applies ONLY to write_memory calls that would CREATE a new memory.
    Edits/overwrites of existing memories, WM_ session files, and content
    carrying the [new-memory-justified: <reason>] override always pass.
    """
    if not str(tool_name).endswith("write_memory"):
        return None
    tool_input = tool_input or {}
    name = str(tool_input.get("memory_name", "")).strip()
    if not name:
        return None
    if name.replace("\\", "/").rsplit("/", 1)[-1].startswith("WM_"):
        return None  # session working memory, not a knowledge memory
    if NEW_MEMORY_OVERRIDE_RE.search(str(tool_input.get("content", ""))):
        return None
    if not cwd or not os.path.isdir(cwd):
        return None
    if memory_exists(cwd, name):
        return None  # updating an existing memory always passes
    tokens = memory_topic_tokens(name)
    if not tokens:
        return None
    hits = find_on_topic_memories(cwd, tokens)
    if not hits:
        return None
    return (
        "🛑 BLOCKED: An on-topic memory already exists: {hits}. "
        "Update it (edit_memory {first}) instead of creating a duplicate. "
        "Override only with literal tag [new-memory-justified: <reason>] "
        "in the content.".format(hits=", ".join(hits), first=hits[0])
    )


# ---------------------------------------------------------------------------
# Change Set H — obligations-digest enforcement
# ---------------------------------------------------------------------------
# Prefixes that REQUIRE an `obligations:` front-matter field. All other
# prefixes (arch/, spec/, wf/, index/, sys/, feedback/, ...) are optional.
RULE_BEARING_PREFIXES = ("dom/", "ref/", "dev/", "feature/")

# Front-matter block: opening '---', then an `obligations:` key as a top-level
# sibling of `description:` (2-space-or-less indent, not nested under
# metadata:), before the closing '---'.
_FRONT_MATTER_BLOCK_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_OBLIGATIONS_FIELD_RE = re.compile(r"^obligations:", re.MULTILINE)

OBLIGATIONS_FIELD_GRAMMAR = (
    "obligations:\n"
    "  - <imperative obligation, one line, concrete>\n"
    "(top-level sibling of `description`; `obligations: []` declares a "
    "conscious none)"
)


def _memory_prefix(memory_name_or_path):
    """Normalize a memory_name or file_path to its 'prefix/' dir segment
    (e.g. 'dom/', 'ref/'), or '' when there is no dir segment."""
    name = str(memory_name_or_path or "").replace("\\", "/").strip()
    # A file_path may carry the full .serena/memory/<prefix>/NAME.md shape —
    # take the segment immediately before the basename.
    parts = [p for p in name.split("/") if p]
    if len(parts) < 2:
        return ""
    return parts[-2].lower() + "/"


def _has_obligations_field(content):
    """True when the front-matter block contains a top-level `obligations:`
    field (list or `[]`)."""
    match = _FRONT_MATTER_BLOCK_RE.match(str(content or "").lstrip("﻿"))
    if not match:
        return False
    return bool(_OBLIGATIONS_FIELD_RE.search(match.group(1)))


def missing_obligations_reason(memory_name_or_path, content):
    """Return the deny message when `content` authors/overwrites a
    rule-bearing memory with no `obligations:` front-matter field, else None.

    Applies only to prefixes in RULE_BEARING_PREFIXES; callers are
    responsible for gating this to CREATE/overwrite (not edit_memory).
    """
    prefix = _memory_prefix(memory_name_or_path)
    if prefix not in RULE_BEARING_PREFIXES:
        return None
    if _has_obligations_field(content):
        return None
    return (
        "🛑 BLOCKED: \"{name}\" is a rule-bearing memory (prefix: {prefix}) "
        "with no `obligations:` front-matter field. Add it — a top-level "
        "sibling of `description`:\n{grammar}\n"
        "`obligations: []` is the conscious-none escape when this memory "
        "truly carries no obligations. This digest is what the two-tier "
        "sweep plans from without a full body read.".format(
            name=memory_name_or_path, prefix=prefix,
            grammar=OBLIGATIONS_FIELD_GRAMMAR,
        )
    )


def _is_memory_md_path_under_serena(file_path):
    """True when file_path looks like a *.md write under a /.serena/memory/
    tree (direct Write bypass of write_memory)."""
    p = str(file_path or "").replace("\\", "/")
    return bool(p) and p.endswith(".md") and "/.serena/memory/" in p


def obligations_denial_for_write(tool_name, tool_input):
    """Change Set H verdict for a write_memory or direct Write call, or None.

    write_memory: denies on CREATE or OVERWRITE (both are full authoring —
    edit_memory partial edits are exempt and never reach this check).
    Direct Write: denies when file_path is a *.md under a /.serena/memory/
    path (the write_memory bypass this gate also has to cover).
    """
    tool_input = tool_input or {}
    name = str(tool_name or "")
    if name.endswith("write_memory"):
        memory_name = tool_input.get("memory_name", "")
        content = tool_input.get("content", "")
        return missing_obligations_reason(memory_name, content)
    if name.endswith("Write") and not name.endswith("write_memory"):
        file_path = tool_input.get("file_path", "")
        if not _is_memory_md_path_under_serena(file_path):
            return None
        content = tool_input.get("content", "")
        return missing_obligations_reason(file_path, content)
    return None


# ---------------------------------------------------------------------------
# FOURTH DUTY — site-data denial
# ---------------------------------------------------------------------------
# IPv4: 4 dot-separated 0-255 octets, not adjacent to another ".digit" on
# either side (rejects version strings like 1.2.3.4.5 or 10.20.30.40.50).
_IPV4_RE = re.compile(
    r"(?<!\d\.)(?<!\.\d)\b"
    r"(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?:\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}"
    r"\b(?!\.\d)"
)

# Documentation/placeholder IPv4 ranges — never denied.
_IPV4_ALLOWED_RANGES = (
    "127.",           # loopback 127.0.0.0/8
    "0.0.0.0",        # unspecified
    "192.0.2.",       # RFC 5737 TEST-NET-1
    "198.51.100.",    # RFC 5737 TEST-NET-2
    "203.0.113.",     # RFC 5737 TEST-NET-3
)

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)

# Placeholder email domains (suffix match on the domain part) — never denied.
_EMAIL_ALLOWED_DOMAIN_SUFFIXES = (
    "example.com", "example.org", "example.net", "example",
    "test", "invalid", "localhost", "local",
)
_EMAIL_ALLOWED_EXACT = ("noreply@anthropic.com",)

# scheme://user:pass@host credentialed URL. Angle-bracket placeholders like
# https://<token>@host are excluded (userinfo must not start with '<').
_URL_CREDENTIAL_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]*://(?!<)[^\s/:@<>]+:[^\s/@<>]+@[^\s/<>]+"
)

# SSH connect strings: "ssh user@host[:port]" (ssh-prefixed) or
# "user@host:port"/"user@host:path" (colon-suffixed — distinguishes it from a
# bare email address, which this pattern otherwise would also match).
_SSH_CONNECT_RE = re.compile(
    r"\bssh\s+[A-Za-z0-9._-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})(?::\S+)?\b"
    r"|"
    r"\b[A-Za-z0-9._-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,}):\S+"
)

_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")

_TOKEN_PREFIX_RES = (
    ("GitHub PAT (classic)", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("GitHub PAT (fine-grained)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("OpenAI-style secret key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)

def _is_placeholder_host(host):
    """True when host (domain, no path/port) is a documentation placeholder."""
    h = str(host or "").lower().rstrip(".")
    return any(h == suf or h.endswith("." + suf) for suf in _EMAIL_ALLOWED_DOMAIN_SUFFIXES)


def _find_ipv4_hits(text):
    hits = []
    for m in _IPV4_RE.finditer(text):
        val = m.group(0)
        if any(val.startswith(pfx) for pfx in _IPV4_ALLOWED_RANGES):
            continue
        hits.append(("IPv4 address", val))
    return hits


def _find_email_hits(text, credential_spans=()):
    hits = []
    for m in _EMAIL_RE.finditer(text):
        val = m.group(0)
        domain = m.group(1)
        if val.lower() in _EMAIL_ALLOWED_EXACT:
            continue
        if _is_placeholder_host(domain):
            continue
        # Already reported as the userinfo of a credentialed URL — don't
        # double-report the same span as a bare email too.
        if any(start <= m.start() and m.end() <= end for start, end in credential_spans):
            continue
        # "git@github.com:<org>/<repo>" — placeholder org/repo path after a
        # colon immediately following the matched host; the SSH detector's
        # placeholder rule governs this shape, not the plain email rule.
        tail = text[m.end():m.end() + 2]
        if domain.lower().rstrip(".") == "github.com" and tail.startswith(":<"):
            continue
        hits.append(("email address", val))
    return hits


def _find_url_credential_hits(text):
    return [(m.start(), m.end(), m.group(0)) for m in _URL_CREDENTIAL_RE.finditer(text)]


def _find_ssh_hits(text):
    hits = []
    for m in _SSH_CONNECT_RE.finditer(text):
        host = m.group(1) or m.group(2)
        if _is_placeholder_host(host):
            continue
        if host.lower().rstrip(".") == "github.com" and "<" in m.group(0):
            continue  # git@github.com:<org>/<repo> placeholder
        hits.append(("SSH connect string", m.group(0)))
    return hits


def _find_private_key_hits(text):
    return [("private key block", m.group(0)) for m in _PRIVATE_KEY_RE.finditer(text)]


def _find_token_hits(text):
    hits = []
    for label, rx in _TOKEN_PREFIX_RES:
        for m in rx.finditer(text):
            hits.append((label, m.group(0)))
    return hits


def find_site_data_hits(text):
    """Return a list of (category, matched_value) for every site-data hit in
    text, across all detectors. Pure scan — no filesystem, no network."""
    text = str(text or "")
    hits = []
    hits.extend(_find_private_key_hits(text))
    hits.extend(_find_token_hits(text))
    url_credential_spans = _find_url_credential_hits(text)
    hits.extend(("credentialed URL", val) for _s, _e, val in url_credential_spans)
    hits.extend(_find_ssh_hits(text))
    hits.extend(_find_email_hits(
        text, credential_spans=[(s, e) for s, e, _v in url_credential_spans]))
    hits.extend(_find_ipv4_hits(text))
    return hits


def _truncate(value, limit=40):
    value = str(value)
    return value if len(value) <= limit else value[:limit] + "…"


def site_data_denial(tool_name, tool_input):
    """FOURTH DUTY verdict: the deny message, or None to allow.

    Scans the same content-bearing field(s) the other duties scan:
    write_memory/edit_memory (content/repl, both server prefixes) and direct
    Edit/Write of a *.md under a /.serena/memory/ tree (new_string/content).
    No override tag — site data is never an acceptable memory write.
    """
    tool_input = tool_input or {}
    name = str(tool_name or "")
    if name.endswith("write_memory") or name.endswith("edit_memory"):
        blob = " ".join(str(tool_input.get(k, "")) for k in ("content", "repl"))
    elif name.endswith("Edit") or name.endswith("Write"):
        file_path = tool_input.get("file_path", "")
        if not _is_memory_md_path_under_serena(file_path):
            return None
        blob = " ".join(str(tool_input.get(k, ""))
                         for k in ("new_string", "content"))
    else:
        return None

    hits = find_site_data_hits(blob)
    if not hits:
        return None

    lines = "\n".join(
        "  - {cat}: {val}".format(cat=cat, val=_truncate(val)) for cat, val in hits
    )
    return (
        "🛑 BLOCKED: this write contains site-specific infrastructure data:\n"
        "{lines}\n"
        "Replace each with a placeholder (host.example, 192.0.2.10, "
        "user@example.test, <token>) and re-issue the write. No override — "
        "site data is never acceptable in a memory. See "
        "`mem:ref/REF_NO_SITE_DATA`.".format(lines=lines)
    )


def targets_memory_index(tool_input):
    """True when the call writes the MEMORY.md index (by memory name or path)."""
    memory_name = str(tool_input.get("memory_name", ""))
    if memory_name in ("MEMORY", "MEMORY.md"):
        return True
    file_path = str(tool_input.get("file_path", ""))
    return os.path.basename(file_path.replace("\\", "/")) == "MEMORY.md"


def written_category_links(tool_input):
    """Return the non-indexed categories the written content would link."""
    blob = " ".join(str(tool_input.get(k, "")) for k in CONTENT_FIELDS)
    found = set()
    for match in _CATEGORY_DIR_LINK.finditer(blob):
        seg = match.group(0).lower()
        for cat in NON_INDEXED_CATEGORIES:
            if cat + "/" in seg:
                found.add(cat)
    if _CATEGORY_FILE_LINK.search(blob):
        for cat in NON_INDEXED_CATEGORIES:
            if re.search(r"\]\([^)/]*\b%s_" % cat.upper(), blob):
                found.add(cat)
    return sorted(found)


def main():
    try:
        input_data = read_stdin_safe(timeout_seconds=2.0)
        tool_name = str(input_data.get("tool_name", ""))
        tool_input = input_data.get("tool_input", {}) or {}

        # FOURTH DUTY — site-data denial: runs first, ahead of every other
        # check, on ANY matched write (MEMORY.md-targeted or not). No
        # override; a hit here always denies regardless of target.
        site_data_denial_msg = site_data_denial(tool_name, tool_input)
        if site_data_denial_msg:
            output = HookOutput(event_name="PreToolUse")
            output.block(site_data_denial_msg)
            output.output_and_exit()
            return

        if not targets_memory_index(tool_input):
            # Change Set H — obligations-digest enforcement: runs first, in
            # addition to (not instead of) the B4 dedupe check below.
            obligations_denial = obligations_denial_for_write(tool_name, tool_input)
            if obligations_denial:
                output = HookOutput(event_name="PreToolUse")
                output.block(obligations_denial)
                output.output_and_exit()
                return

            # B4 — new-memory dedupe: deny a write_memory creating a memory
            # whose topic an existing memory already covers.
            cwd = str(input_data.get("cwd", "") or "") or os.getcwd()
            denial = new_memory_dedupe_denial(tool_name, tool_input, cwd)
            if denial:
                output = HookOutput(event_name="PreToolUse")
                output.block(denial)
                output.output_and_exit()
                return
            output_empty()
            return

        leaked = written_category_links(tool_input)
        if not leaked:
            output_empty()
            return

        output = HookOutput(event_name="PreToolUse")
        output.block(
            "🛑 BLOCKED: this write adds {cats} link(s) to MEMORY.md.\n"
            "MEMORY.md is the auto-loaded session index — spec/report/research/"
            "project memories are NEVER indexed there. They are discovered via "
            "list_memories(topic=\"spec\"|\"report\"|\"research\"|\"project\") "
            "when a task explicitly needs them.\n"
            "Remove the {cats} link(s) from your update and re-issue it; the "
            "memory itself stays where it is.".format(cats="/".join(leaked))
        )
        output.output_and_exit()

    except Exception as e:
        output = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": f"Memory-index gate error: {e}"}}
        print(json.dumps(output), file=sys.stdout)
        sys.exit(0)


if __name__ == "__main__":
    main()
