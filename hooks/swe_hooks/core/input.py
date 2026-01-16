"""Safe stdin reading with timeout protection."""

import sys
import json
import select
from typing import Dict, Any, Optional


def read_stdin_safe(timeout_seconds: float = 5.0) -> Dict[str, Any]:
    """Read JSON from stdin with timeout protection.

    Returns empty dict if no input available or on error.
    """
    try:
        # Check if stdin has data available (Unix only)
        if hasattr(select, 'select'):
            ready, _, _ = select.select([sys.stdin], [], [], timeout_seconds)
            if not ready:
                return {}

        # Read and parse JSON
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}

        return json.loads(raw)

    except json.JSONDecodeError:
        return {}
    except Exception:
        return {}


def get_input_field(input_data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get nested field from input data."""
    current = input_data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key, default)
        else:
            return default
    return current if current is not None else default
