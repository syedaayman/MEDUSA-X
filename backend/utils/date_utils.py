"""Date utility placeholders."""

from datetime import date


def normalize_date(value: str) -> date:
    """Parse an ISO-8601 calendar date."""
    return date.fromisoformat(value)
