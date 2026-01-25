#!/usr/bin/env python3
"""Test suite for WM Background Writer.

Tests:
1. Format validation (anti-pattern detection)
2. Async behavior (main thread doesn't block)
3. Write coalescing
4. Session isolation
5. Error recovery
"""

import os
import sys
import time
import tempfile
import threading
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wm_validator import WMFormatValidator, get_validator
from wm_writer_daemon import (
    WMBackgroundWriter, WriteOperation, async_wm_write,
    get_wm_writer, shutdown_wm_writer
)


def test_filename_validation():
    """Test WM filename validation."""
    print("\n=== Test: Filename Validation ===")
    validator = get_validator()

    # Valid filenames
    valid_cases = [
        "WM_3fe6b3c5_theme_refactor.md",
        "WM_abcd1234_test.md",
        "WM_12345678_multi_word_desc.md",
    ]

    for filename in valid_cases:
        is_valid, error, session_id = validator.validate_filename(filename)
        assert is_valid, f"Should be valid: {filename}, got error: {error}"
        print(f"  ✓ Valid: {filename} (session: {session_id})")

    # Invalid filenames
    invalid_cases = [
        "WM_short_desc.md",  # Session ID too short
        "working_memory_3fe6b3c5_test.md",  # Wrong prefix case
        "MEMORY_3fe6b3c5_test.md",  # Missing WORKING_
        "WM_3fe6b3c5.md",  # Missing descriptor
    ]

    for filename in invalid_cases:
        is_valid, error, _ = validator.validate_filename(filename)
        assert not is_valid, f"Should be invalid: {filename}"
        print(f"  ✓ Invalid: {filename} - {error}")

    print("  ✅ Filename validation tests passed!")


def test_content_validation():
    """Test WM content validation."""
    print("\n=== Test: Content Validation ===")
    validator = get_validator()

    # Valid content with required sections
    valid_content = """# Working Memory

## Chat: test_task
Session: 3fe6b3c5

## Workflow Context
- **Current State**: WF_EXECUTE
- **Session ID**: 3fe6b3c5

## Current Task
**[IN PROGRESS]**: Test Task

### Progress
- [x] Step 1
- [ ] Step 2
"""

    is_valid, errors = validator.validate_content(valid_content)
    assert is_valid, f"Should be valid, got errors: {errors}"
    print(f"  ✓ Valid content passes validation")

    # Invalid content (missing required sections)
    invalid_content = """# Working Memory

## Chat: test_task

Some random content without proper sections.
"""

    is_valid, errors = validator.validate_content(invalid_content)
    assert not is_valid, "Should be invalid - missing required sections"
    print(f"  ✓ Invalid content rejected: {errors}")

    print("  ✅ Content validation tests passed!")


def test_single_field_edit_detection():
    """Test anti-pattern detection for single-field state edits."""
    print("\n=== Test: Single-Field Edit Detection (Anti-Pattern) ===")
    validator = get_validator()

    base_content = """# Working Memory

## Workflow Context
- **Current State**: WF_EXECUTE
- **Session ID**: 3fe6b3c5

## Current Task
**[IN PROGRESS]**: Test Task

### Progress
- [x] Step 1
- [ ] Step 2
"""

    # Single-field state edit (SHOULD BE DETECTED)
    single_field_edit = base_content.replace(
        "**Current State**: WF_EXECUTE",
        "**Current State**: WF_VERIFY"
    )

    is_violation, msg = validator.detect_single_field_edit(base_content, single_field_edit)
    assert is_violation, "Should detect single-field state edit as violation"
    print(f"  ✓ Single-field edit detected: {msg}")

    # Multi-section edit (SHOULD NOT BE DETECTED)
    multi_section_edit = base_content.replace(
        "**Current State**: WF_EXECUTE",
        "**Current State**: WF_VERIFY"
    ).replace(
        "- [ ] Step 2",
        "- [x] Step 2"
    ).replace(
        "[IN PROGRESS]",
        "[COMPLETED]"
    )

    is_violation, msg = validator.detect_single_field_edit(base_content, multi_section_edit)
    assert not is_violation, f"Should NOT detect multi-section edit as violation, got: {msg}"
    print(f"  ✓ Multi-section edit allowed")

    print("  ✅ Anti-pattern detection tests passed!")


def test_session_ownership():
    """Test session ownership validation."""
    print("\n=== Test: Session Ownership ===")
    validator = get_validator()

    content = """# Working Memory
Session: 3fe6b3c5

## Workflow Context
- **Session ID**: 3fe6b3c5
"""

    # Matching session
    is_valid, error = validator.validate_session_ownership(content, "3fe6b3c5")
    assert is_valid, f"Should validate matching session, got: {error}"
    print(f"  ✓ Matching session validated")

    # Non-matching session
    is_valid, error = validator.validate_session_ownership(content, "different1")
    assert not is_valid, "Should reject non-matching session"
    print(f"  ✓ Non-matching session rejected: {error}")

    print("  ✅ Session ownership tests passed!")


def test_async_write():
    """Test async write functionality."""
    print("\n=== Test: Async Write ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test_wm.md")

        content = """# Working Memory

## Workflow Context
- **Current State**: WF_EXECUTE

## Current Task
Test
"""

        # Test async write
        start = time.time()
        success = async_wm_write(
            filepath=test_file,
            content=content,
            operation_type='full_write',
            validate=False,
        )
        elapsed = time.time() - start

        assert success, "Async write should succeed"
        print(f"  ✓ Async write queued in {elapsed*1000:.2f}ms")

        # Wait for write to complete
        time.sleep(0.2)

        assert os.path.exists(test_file), "File should be created"
        with open(test_file, 'r') as f:
            written = f.read()
        assert written == content, "Content should match"
        print(f"  ✓ File written correctly")

    # Shutdown writer
    shutdown_wm_writer()
    print("  ✅ Async write tests passed!")


def test_write_coalescing():
    """Test that rapid writes to same file are coalesced."""
    print("\n=== Test: Write Coalescing ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "coalesce_test.md")

        writer = WMBackgroundWriter(coalesce_window_ms=100)
        writer.start()

        # Queue multiple rapid writes
        for i in range(5):
            writer.queue_write(WriteOperation(
                filepath=test_file,
                content=f"Content version {i}",
                operation_type='full_write',
                validate=False,
            ))

        # Wait for writes to complete
        time.sleep(0.3)

        stats = writer.get_stats()
        print(f"  Stats: {stats}")

        # Should have coalesced some writes
        assert stats['coalesced'] > 0, "Should have coalesced writes"
        print(f"  ✓ Coalesced {stats['coalesced']} writes")

        # File should have final content
        with open(test_file, 'r') as f:
            content = f.read()
        assert "version 4" in content, f"Should have final version, got: {content}"
        print(f"  ✓ Final content is correct")

        writer.stop()

    print("  ✅ Write coalescing tests passed!")


def test_error_recovery():
    """Test that writer recovers from errors."""
    print("\n=== Test: Error Recovery ===")

    writer = WMBackgroundWriter()
    writer.start()

    # Try to write to invalid path
    success = writer.queue_write(WriteOperation(
        filepath="/nonexistent/path/that/should/fail/test.md",
        content="test",
        operation_type='full_write',
        validate=False,
    ))

    assert success, "Queue should accept the write"
    time.sleep(0.2)

    stats = writer.get_stats()
    assert stats['failed'] > 0, "Should have recorded failure"
    print(f"  ✓ Error handled gracefully (failed: {stats['failed']})")

    # Writer should still be running
    assert writer.is_running(), "Writer should still be running after error"
    print(f"  ✓ Writer still running after error")

    writer.stop()
    print("  ✅ Error recovery tests passed!")


def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("WM Background Writer Test Suite")
    print("=" * 60)

    try:
        test_filename_validation()
        test_content_validation()
        test_single_field_edit_detection()
        test_session_ownership()
        test_async_write()
        test_write_coalescing()
        test_error_recovery()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        shutdown_wm_writer()


if __name__ == '__main__':
    sys.exit(run_all_tests())
