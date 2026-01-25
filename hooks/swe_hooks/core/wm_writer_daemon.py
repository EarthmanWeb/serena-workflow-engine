"""Background writer for async Working Memory file operations.

Provides non-blocking WM writes by queueing operations to a daemon thread.
Validates format against REF_WM specs before writing.
"""

import queue
import threading
import time
import sys
import os
from dataclasses import dataclass, field
from typing import Literal, Optional, List, Callable
from pathlib import Path

try:
    from .wm_validator import WMFormatValidator, get_validator
except ImportError:
    # Fallback for direct execution
    from wm_validator import WMFormatValidator, get_validator


@dataclass
class WriteOperation:
    """Represents a queued write operation."""
    filepath: str
    content: str
    operation_type: Literal['full_write', 'state_update', 'edit_tracking', 'transition_log', 'append']
    timestamp: float = field(default_factory=time.time)
    validate: bool = True
    session_id: Optional[str] = None
    old_content: Optional[str] = None  # For anti-pattern detection
    callback: Optional[Callable[[bool, str], None]] = None  # Optional completion callback


class WMBackgroundWriter:
    """Background thread for async Working Memory writes.

    Features:
    - Non-blocking queue-based writes
    - Format validation before writing
    - Write coalescing for rapid updates
    - Graceful error handling
    - Auto-restart on thread failure
    """

    def __init__(self, max_queue_size: int = 100, coalesce_window_ms: int = 50):
        """Initialize background writer.

        Args:
            max_queue_size: Maximum pending operations (oldest dropped on overflow)
            coalesce_window_ms: Time window to batch writes to same file
        """
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._validator = get_validator()
        self._coalesce_window = coalesce_window_ms / 1000.0
        self._lock = threading.Lock()
        self._stats = {
            'queued': 0,
            'written': 0,
            'failed': 0,
            'coalesced': 0,
            'validation_rejected': 0,
        }

    def start(self) -> bool:
        """Start the background writer thread.

        Returns:
            True if started successfully, False if already running
        """
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return False

            self._running = True
            self._thread = threading.Thread(
                target=self._writer_loop,
                name="WMBackgroundWriter",
                daemon=True  # Dies with main process
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> bool:
        """Stop the background writer gracefully.

        Args:
            timeout: Max seconds to wait for pending writes

        Returns:
            True if stopped cleanly, False if timed out
        """
        self._running = False

        if self._thread and self._thread.is_alive():
            # Signal thread to stop by putting None
            try:
                self._queue.put(None, timeout=0.1)
            except queue.Full:
                pass

            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()

        return True

    def queue_write(self, operation: WriteOperation) -> bool:
        """Queue a write operation for async execution.

        Args:
            operation: The write operation to queue

        Returns:
            True if queued successfully, False if queue full (oldest dropped)
        """
        # Auto-start if not running
        if not self._running or not self._thread or not self._thread.is_alive():
            self.start()

        try:
            self._queue.put_nowait(operation)
            self._stats['queued'] += 1
            return True
        except queue.Full:
            # Drop oldest and retry
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(operation)
                self._stats['queued'] += 1
                return True
            except (queue.Empty, queue.Full):
                return False

    def _writer_loop(self):
        """Main writer loop - processes queue until stopped."""
        pending: List[WriteOperation] = []

        while self._running:
            try:
                # Wait for operation with timeout
                try:
                    op = self._queue.get(timeout=0.1)
                except queue.Empty:
                    # Process any pending coalesced writes
                    if pending:
                        self._process_coalesced(pending)
                        pending = []
                    continue

                # None signals shutdown
                if op is None:
                    break

                # Check for coalescing opportunity
                if pending and pending[-1].filepath == op.filepath:
                    # Same file - coalesce by keeping latest
                    pending[-1] = op
                    self._stats['coalesced'] += 1
                else:
                    # Different file - flush pending and add new
                    if pending:
                        self._process_coalesced(pending)
                        pending = []
                    pending.append(op)

                # If we've waited long enough, flush
                if pending and (time.time() - pending[0].timestamp) > self._coalesce_window:
                    self._process_coalesced(pending)
                    pending = []

            except Exception as e:
                self._log_error(f"Writer loop error: {e}")
                self._stats['failed'] += 1

        # Flush remaining on shutdown
        if pending:
            self._process_coalesced(pending)

    def _process_coalesced(self, operations: List[WriteOperation]):
        """Process a batch of coalesced operations."""
        for op in operations:
            self._execute_write(op)

    def _execute_write(self, op: WriteOperation):
        """Execute a single write operation with validation."""
        success = False
        error_msg = ""

        try:
            # Validate if requested
            if op.validate:
                # Check for anti-pattern (single-field state edit)
                if op.old_content and op.operation_type == 'state_update':
                    is_violation, violation_msg = self._validator.detect_single_field_edit(
                        op.old_content, op.content
                    )
                    if is_violation:
                        self._stats['validation_rejected'] += 1
                        error_msg = f"Validation rejected: {violation_msg}"
                        self._log_error(error_msg)
                        if op.callback:
                            op.callback(False, error_msg)
                        return

                # Validate content structure
                is_valid, errors = self._validator.validate_content(op.content)
                if not is_valid and op.operation_type == 'full_write':
                    # Only reject full writes for missing sections
                    # Partial updates (edit_tracking, transition_log) can skip this
                    self._log_error(f"Validation warnings: {errors}")

                # Validate session ownership if session_id provided
                if op.session_id:
                    is_valid, error = self._validator.validate_session_ownership(
                        op.content, op.session_id
                    )
                    if not is_valid:
                        self._stats['validation_rejected'] += 1
                        error_msg = f"Session validation failed: {error}"
                        self._log_error(error_msg)
                        if op.callback:
                            op.callback(False, error_msg)
                        return

            # Ensure directory exists
            filepath = Path(op.filepath)
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(op.content)

            self._stats['written'] += 1
            success = True

        except IOError as e:
            self._stats['failed'] += 1
            error_msg = f"IO error writing {op.filepath}: {e}"
            self._log_error(error_msg)
        except Exception as e:
            self._stats['failed'] += 1
            error_msg = f"Error writing {op.filepath}: {e}"
            self._log_error(error_msg)

        # Call completion callback if provided
        if op.callback:
            op.callback(success, error_msg)

    def _log_error(self, message: str):
        """Log error to stderr."""
        print(f"[WMBackgroundWriter] {message}", file=sys.stderr)

    def get_stats(self) -> dict:
        """Get writer statistics."""
        return dict(self._stats)

    def is_running(self) -> bool:
        """Check if writer thread is running."""
        return self._running and self._thread is not None and self._thread.is_alive()

    def pending_count(self) -> int:
        """Get number of pending writes in queue."""
        return self._queue.qsize()


# Singleton instance
_wm_writer: Optional[WMBackgroundWriter] = None
_writer_lock = threading.Lock()


def get_wm_writer() -> WMBackgroundWriter:
    """Get or create singleton background writer."""
    global _wm_writer
    with _writer_lock:
        if _wm_writer is None:
            _wm_writer = WMBackgroundWriter()
            _wm_writer.start()
        elif not _wm_writer.is_running():
            _wm_writer.start()
        return _wm_writer


def async_wm_write(
    filepath: str,
    content: str,
    operation_type: Literal['full_write', 'state_update', 'edit_tracking', 'transition_log', 'append'] = 'full_write',
    validate: bool = True,
    session_id: Optional[str] = None,
    old_content: Optional[str] = None,
    callback: Optional[Callable[[bool, str], None]] = None
) -> bool:
    """Queue an async WM write operation.

    This function returns immediately - the actual write happens in background.

    Args:
        filepath: Path to the WM file
        content: Content to write
        operation_type: Type of operation for validation logic
        validate: Whether to validate format before writing
        session_id: Optional session ID for ownership validation
        old_content: Previous content for anti-pattern detection
        callback: Optional callback(success, error_msg) called after write

    Returns:
        True if queued successfully, False if queue full
    """
    writer = get_wm_writer()
    op = WriteOperation(
        filepath=filepath,
        content=content,
        operation_type=operation_type,
        validate=validate,
        session_id=session_id,
        old_content=old_content,
        callback=callback,
    )
    return writer.queue_write(op)


def async_wm_append(
    filepath: str,
    append_content: str,
    session_id: Optional[str] = None
) -> bool:
    """Queue an async append operation to a WM file.

    Reads current content and appends new content.

    Args:
        filepath: Path to the WM file
        append_content: Content to append
        session_id: Optional session ID for validation

    Returns:
        True if queued successfully
    """
    # Read current content synchronously (small files, fast)
    current_content = ""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                current_content = f.read()
    except IOError:
        pass

    new_content = current_content + append_content

    return async_wm_write(
        filepath=filepath,
        content=new_content,
        operation_type='append',
        validate=False,  # Append doesn't need full validation
        session_id=session_id,
    )


def shutdown_wm_writer(timeout: float = 2.0) -> bool:
    """Shutdown the background writer gracefully.

    Call this on process exit to ensure pending writes complete.

    Args:
        timeout: Max seconds to wait

    Returns:
        True if shutdown cleanly
    """
    global _wm_writer
    with _writer_lock:
        if _wm_writer:
            result = _wm_writer.stop(timeout)
            _wm_writer = None
            return result
        return True
