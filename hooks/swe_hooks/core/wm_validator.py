"""Working Memory format validator.

Validates WM content against REF_WM specs:
- Multi-section updates (rejects single-field state edits)
- Required sections check
- Naming convention enforcement
- Session ID validation
"""

import re
from typing import Tuple, Optional, List, Set


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

    # Fields that indicate state-only changes (anti-pattern if changed alone)
    # These patterns match with or without markdown bold formatting
    STATE_FIELD_PATTERNS = [
        r'Current State',
        r'Calling Step',
        r'Return Step',
        r'Invocation Mode',
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

    def detect_single_field_edit(self, old_content: str, new_content: str) -> Tuple[bool, str]:
        """Detect anti-pattern: single-field state edits.

        Per REF_WM: "SINGLE-FIELD STATE EDIT = WORKFLOW VIOLATION"

        Args:
            old_content: Previous WM content
            new_content: New WM content

        Returns:
            Tuple of (is_violation, violation_description)
        """
        if not old_content or not new_content:
            return False, ""

        old_lines = old_content.strip().split('\n')
        new_lines = new_content.strip().split('\n')

        # Find changed lines
        old_set = set(old_lines)
        new_set = set(new_lines)

        removed = old_set - new_set
        added = new_set - old_set

        # Filter out empty lines and whitespace-only changes
        removed = {line for line in removed if line.strip()}
        added = {line for line in added if line.strip()}

        total_changes = len(removed) + len(added)

        # If very few lines changed, check if they're all state fields
        if total_changes <= 4:
            all_changes = removed | added
            state_field_changes = 0

            for line in all_changes:
                line_stripped = line.strip()
                if any(field in line_stripped for field in self.STATE_FIELD_PATTERNS):
                    state_field_changes += 1

            # If ALL changes are state field changes, it's a violation
            if state_field_changes > 0 and state_field_changes == len(all_changes):
                return True, f"Single-field state edit detected. Changed only: {', '.join(self.STATE_FIELD_PATTERNS[:state_field_changes])}"

        return False, ""

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

    def get_sections_modified(self, old_content: str, new_content: str) -> Set[str]:
        """Identify which sections were modified between old and new content.

        Args:
            old_content: Previous WM content
            new_content: New WM content

        Returns:
            Set of section names that were modified
        """
        modified = set()

        # Define section markers
        section_markers = [
            ('Workflow Context', r'##\s*Workflow Context'),
            ('Current Task', r'##\s*Current Task'),
            ('Progress', r'###?\s*Progress'),
            ('Previous Task', r'##\s*Previous Task'),
            ('Files', r'\*\*Files'),
            ('Context', r'###?\s*Context'),
            ('Artifacts', r'\*\*Artifacts'),
        ]

        for section_name, pattern in section_markers:
            # Extract section content from both
            old_section = self._extract_section(old_content, pattern)
            new_section = self._extract_section(new_content, pattern)

            if old_section != new_section:
                modified.add(section_name)

        return modified

    def _extract_section(self, content: str, section_pattern: str) -> str:
        """Extract content of a section from WM content."""
        if not content:
            return ""

        # Find section start
        match = re.search(section_pattern, content, re.IGNORECASE)
        if not match:
            return ""

        start = match.end()

        # Find next section (## marker)
        next_section = re.search(r'\n##\s', content[start:])
        if next_section:
            end = start + next_section.start()
        else:
            end = len(content)

        return content[start:end].strip()


# Singleton instance for reuse
_validator: Optional[WMFormatValidator] = None


def get_validator() -> WMFormatValidator:
    """Get or create singleton validator instance."""
    global _validator
    if _validator is None:
        _validator = WMFormatValidator()
    return _validator
