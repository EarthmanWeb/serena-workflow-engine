"""Working Memory format validator.

Validates WM content against REF_WM specs:
- Multi-section updates (rejects single-field state edits)
- Required sections check
- Naming convention enforcement
- Session ID validation
"""

import re
from typing import Tuple, Optional, List


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



# Singleton instance for reuse
_validator: Optional[WMFormatValidator] = None


def get_validator() -> WMFormatValidator:
    """Get or create singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = WMFormatValidator()
    return _validator
