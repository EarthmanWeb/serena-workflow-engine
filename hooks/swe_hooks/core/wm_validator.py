"""Working Memory format validator.

Validates WM content against REF_WM specs:
- Multi-section updates (rejects single-field state edits)
- Required sections check
- Naming convention enforcement
- Session ID validation
"""

import re
from typing import Tuple, Optional, List


# Ticket-ID pattern: a project prefix (uppercase letters/digits, starting
# with a letter) + '-' + digits, e.g. SPS-855, AB1-12. Word-boundaried so it
# never matches inside a longer token.
TICKET_ID_RE = re.compile(r'\b[A-Z][A-Z0-9]+-\d+\b')

# A numbered or bulleted list item under Current Task, e.g. "1. fix X" or
# "- fix Y" / "* fix Y". Matched per-line; counting DISTINCT list items (not
# occurrences of the marker elsewhere) is the caller's job.
LIST_ITEM_RE = re.compile(r'^\s*(?:\d+[.)]|[-*])\s+\S', re.MULTILINE)

# Collective-task phrases implying 2+ independent units without naming
# explicit ticket IDs. The trailing \s+\S captures the first word after the
# quantifier so a bare "all open tickets" (no number) still counts — N is
# inferred as 2 (the minimum this signal can mean) unless digits are present.
COLLECTIVE_PHRASE_RE = re.compile(
    r'\b(?:all open|each|every|both)\s+(?:tickets?|jobs?|tasks?|issues?)\b'
    r'|\bthese\s+(\d+)\s+(?:tickets?|jobs?|tasks?|issues?)\b',
    re.IGNORECASE,
)


class WMFormatValidator:
    """Validates Working Memory format against REF_WM specs."""

    # Required sections in a valid WM file
    REQUIRED_SECTIONS = [
        'Workflow Context',
        'Current Task',
    ]

    # Optional but recommended sections
    RECOMMENDED_SECTIONS = [
        'Progress',
        'Previous Task',
    ]

    # Naming pattern: WM_<SESSION_ID>.md
    FILENAME_PATTERN = re.compile(
        r'^WM_([a-f0-9]{8})(?:\.md)?$'
    )

    def validate_filename(self, filename: str) -> Tuple[bool, str, Optional[str]]:
        """Validate WM filename format.

        Args:
            filename: The filename to validate (with or without .md extension)

        Returns:
            Tuple of (is_valid, error_message, extracted_session_id)
        """
        match = self.FILENAME_PATTERN.match(filename)
        if not match:
            return False, f"Invalid filename format. Expected: WM_<8-char-session>.md", None

        session_id = match.group(1)
        return True, "", session_id

    def validate_content(self, content: str) -> Tuple[bool, List[str]]:
        """Validate WM content has required sections.

        Args:
            content: The full WM content

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        for section in self.REQUIRED_SECTIONS:
            # Look for ## Section or **Section** patterns
            section_patterns = [
                f'## {section}',
                f'**{section}**',
                f'### {section}',
            ]
            found = any(pattern in content for pattern in section_patterns)
            if not found:
                errors.append(f"Missing required section: {section}")

        # Check for Workflow Context fields (handle markdown bold formatting)
        if '## Workflow Context' in content or '### Workflow Context' in content:
            # Look for Current State with optional markdown formatting
            if not re.search(r'Current State\*?\*?:', content):
                errors.append("Workflow Context missing 'Current State:' field")
            # Look for Session ID with optional markdown formatting
            if not re.search(r'Session(?:\s+ID)?\*?\*?:', content):
                errors.append("Workflow Context missing 'Session ID:' field")

        return len(errors) == 0, errors

    def validate_session_ownership(self, content: str, expected_session_id: str) -> Tuple[bool, str]:
        """Validate that content belongs to the expected session.

        Args:
            content: WM content to check
            expected_session_id: The session ID that should own this WM

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Extract session ID from content
        session_match = re.search(r'Session(?:\s+ID)?:\s*([a-f0-9]{8})', content, re.IGNORECASE)
        if not session_match:
            return False, "No session ID found in content"

        content_session = session_match.group(1).lower()
        expected_lower = expected_session_id.lower()

        if content_session != expected_lower:
            return False, f"Session mismatch: content has {content_session}, expected {expected_lower}"

        return True, ""



def multi_task_signals(current_task_text: str) -> List[str]:
    """Detect evidence that Current Task names 2+ independent tickets/jobs.

    Returns a list of human-readable evidence strings (empty = no signal
    found — single-task or ambiguous text passes). Each evidence category is
    independent; any ONE non-empty category is sufficient to flag the task
    as multi-ticket. Low false-positive rules:

    - 2+ DISTINCT ticket IDs (SPS-855, SPS-856, ...) — the SAME id repeated
      twice counts as ONE unit, not two.
    - A numbered/bulleted list under the text with 2+ items — a single task
      described across several prose lines (no list markers) does not match;
      a single ticket's own sub-steps (e.g. "1. read code  2. write test")
      also matches this rule (documented limitation — list structure alone
      cannot distinguish "N tickets" from "N steps of one ticket").
    - A collective phrase ("all open tickets", "each ticket", "every job",
      "both issues", "these 3 tasks") — implies N>=2 even with no ticket IDs
      enumerated.

    Args:
        current_task_text: the raw text of the WM Current Task section (or
            any task-description text to scan).

    Returns:
        List of evidence strings, e.g. ["2 distinct ticket IDs: SPS-855, SPS-856"].
        Empty list means no multi-task signal detected.
    """
    text = current_task_text or ''
    evidence: List[str] = []

    ticket_ids = sorted(set(TICKET_ID_RE.findall(text)))
    if len(ticket_ids) >= 2:
        evidence.append(f"{len(ticket_ids)} distinct ticket IDs: {', '.join(ticket_ids)}")

    list_items = LIST_ITEM_RE.findall(text)
    if len(list_items) >= 2:
        evidence.append(f"{len(list_items)}-item numbered/bulleted list under Current Task")

    for match in COLLECTIVE_PHRASE_RE.finditer(text):
        n_group = match.group(1)
        n = int(n_group) if n_group else 2
        if n >= 2:
            evidence.append(f"collective phrase implying {n}+ tasks: \"{match.group(0).strip()}\"")

    return evidence


# Singleton instance for reuse
_validator: Optional[WMFormatValidator] = None


def get_validator() -> WMFormatValidator:
    """Get or create singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = WMFormatValidator()
    return _validator
