"""Doc-claims ledger — shared parser + matchers (Change Sets C4/C5/C6).

The WM file carries a '## Doc Claims Used' section: one row per concrete
value (host, path, port, flag) the model pulled out of a memory and acted
on. Row format, one per claim ('->' tolerated wherever '→' appears):

  - mem:<memory-name> → <claim-value> → pending
  - mem:<memory-name> → <claim-value> → confirmed
  - mem:<memory-name> → <claim-value> → corrected → <true value>

Consumers:
  - state_manager._check_doc_claims_gate (C4): pending rows block
    WF_VERIFY/WF_DONE.
  - swe_post_tool_failure (C5): a FAILED Bash/browser/WP-CLI call whose args
    contain a ledger claim value routes the fix through the source memory.
  - swe_post_doc_claims (C6): a SUCCESSFUL Bash call that near-matches a
    claim value (same key, different value) is a silent doc substitution.

Matching is deliberately DUMB and favors false positives — these feed
advisory attachments (deduped per session), never hard denials.

Pure stdlib. parse_claims/pending_claims/claim_in_args/near_match are pure
functions; find_wm_claims and stream_has_event_key do best-effort IO (the
existing stream idiom: any IO failure reads as "no ledger"/"not seen",
never an exception).
"""

import json
import os
import re

# WM section holding the ledger. Rows outside this section are NOT claims.
DOC_CLAIMS_SECTION = "## Doc Claims Used"

_ARROW_SPLIT_RE = re.compile(r'\s*(?:→|->)\s*')
_ROW_RE = re.compile(r'^\s*[-*]\s+(mem:.+)$')
_TOKEN_SPLIT_RE = re.compile(r'[^A-Za-z0-9]+')
_WORD_SPLIT_RE = re.compile(r'[\s"\'`;|&()<>]+')

_STATUSES = ('pending', 'confirmed', 'corrected')

# A claim token must be at least this long to participate in near-matching —
# shorter tokens ('wp', 'db', 'v2') are too generic to signal a substitution.
_DISTINCTIVE_TOKEN_LEN = 4


def parse_claims(wm_content):
    """Parse the '## Doc Claims Used' ledger out of WM content.

    Returns a list of {"name", "claim", "status", "true_value"} dicts, in row
    order. "name" is the memory name WITHOUT the 'mem:' prefix. "true_value"
    is None unless status is 'corrected'. Malformed rows (no 'mem:' lead, a
    missing/unknown status) are skipped, not raised — the ledger is
    model-written free text.
    """
    claims = []
    in_section = False
    for line in str(wm_content or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('## '):
            in_section = stripped == DOC_CLAIMS_SECTION
            continue
        if not in_section:
            continue
        row = _ROW_RE.match(line)
        if not row:
            continue
        parts = _ARROW_SPLIT_RE.split(row.group(1))
        if len(parts) < 3:
            continue
        name = parts[0][len('mem:'):].strip()
        claim = parts[1].strip()
        status = parts[2].strip().lower()
        if not name or not claim or status not in _STATUSES:
            continue
        true_value = None
        if status == 'corrected' and len(parts) > 3:
            # A true value that itself contained an arrow was split further —
            # rejoin (normalized to '→'; a documented, acceptable loss).
            true_value = ' → '.join(p.strip() for p in parts[3:]).strip() or None
        claims.append({'name': name, 'claim': claim,
                       'status': status, 'true_value': true_value})
    return claims


def pending_claims(wm_content):
    """Rows still 'pending' — the C4 VERIFY/DONE gate's blocking set."""
    return [c for c in parse_claims(wm_content) if c['status'] == 'pending']


def blocking_claims(wm_content):
    """Rows that block a WF_VERIFY/WF_DONE transition (C4).

    Blocking: status 'pending', and status 'corrected' with NO recorded true
    value — a row claiming correction without saying what the true value is
    cannot be verified and reads as a dodge. The spec's full second condition
    (corrected with no memory edit recorded this session) is enforceable only
    as doc text: stream 'edit' events carry no memory name, so code cannot
    tell a memory correction from a source edit. WF_VERIFY.md carries that
    obligation.
    """
    return [c for c in parse_claims(wm_content)
            if c['status'] == 'pending'
            or (c['status'] == 'corrected' and not c['true_value'])]


def wm_claims_path(cwd, session_id):
    """Path of the session's WM file under <cwd>/.serena/memories/."""
    return os.path.join(cwd or '', '.serena', 'memories', f'WM_{session_id}.md')


def find_wm_claims(cwd, session_id):
    """Locate WM_<session>.md under .serena/memories/ and parse its ledger.

    Empty list when the WM file (or session id) is absent — a single open()
    attempt, so the no-ledger fast path costs one stat.
    """
    if not session_id:
        return []
    try:
        with open(wm_claims_path(cwd, session_id), 'r') as f:
            content = f.read()
    except OSError:
        return []
    return parse_claims(content)


def claim_in_args(claims, args_text):
    """First claim whose claim-value appears as a substring of args_text.

    Exact containment only (C5: the failing call USED the documented value).
    Claim values shorter than 2 chars never match — they would match
    everything.
    """
    text = str(args_text or '')
    for claim in claims or []:
        value = str(claim.get('claim') or '').strip()
        if len(value) >= 2 and value in text:
            return claim
    return None


def _tokens(text):
    return [t for t in _TOKEN_SPLIT_RE.split(str(text).lower()) if t]


def near_match(claims, args_text):
    """C6's dumb substitution matcher: (claim, used-word) or None.

    For each claim value, tokenize on [^A-Za-z0-9]+. A word of args_text is
    a near match when it is NOT the documented value but either:
      - stem share: one of its tokens and one claim token differ while one
        is a prefix of the other (both >= 4 chars), e.g. 'deploy' vs
        'deployment'; or
      - compound overlap: it shares a distinctive (>= 4 char) token with the
        claim while its token set differs, e.g. documented 'sps-wpms.local'
        vs used 'sps-wpms-master.local'.
    A claim value literally present in args_text is exact use, never a
    substitution. Favors false positives; keeps it dumb.
    """
    text = str(args_text or '')
    text_lower = text.lower()
    words = [w for w in _WORD_SPLIT_RE.split(text) if w]
    for claim in claims or []:
        value = str(claim.get('claim') or '').strip().lower()
        if not value:
            continue
        if value in text_lower:
            continue  # documented value used verbatim — not a substitution
        claim_tokens = set(_tokens(value))
        if not claim_tokens:
            continue
        for word in words:
            word_lower = word.lower()
            if word_lower == value:
                continue
            word_tokens = _tokens(word_lower)
            stem = any(
                wt != ct
                and len(wt) >= _DISTINCTIVE_TOKEN_LEN
                and len(ct) >= _DISTINCTIVE_TOKEN_LEN
                and (wt.startswith(ct) or ct.startswith(wt))
                for wt in word_tokens for ct in claim_tokens)
            shared = any(
                t in claim_tokens and len(t) >= _DISTINCTIVE_TOKEN_LEN
                for t in word_tokens)
            if stem or (shared and set(word_tokens) != claim_tokens):
                return claim, word
    return None


def stream_has_event_key(stream_path, event_type, key):
    """True when the session stream already holds {type: event_type, k: key}.

    The C5/C6 per-session dedupe: one attachment per claim (C5) or per
    (claim, used) pair (C6). Best-effort scan — a missing/unreadable stream
    reads as 'not seen'.
    """
    try:
        with open(stream_path, 'r') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                except (json.JSONDecodeError, ValueError):
                    continue
                if event.get('type') == event_type and event.get('k') == key:
                    return True
    except OSError:
        pass
    return False
