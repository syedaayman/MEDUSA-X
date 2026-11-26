"""Tombstone for the removed Supabase integration.

MEDUSA-X persists everything in SQLite and uses no external database service,
so no Supabase package, URL or secret key is required anywhere in the project.
Nothing imports this module; it is kept only so that any stale import fails with
an explicit message instead of a confusing ModuleNotFoundError.
"""

from __future__ import annotations


def get_supabase_client() -> None:  # pragma: no cover - removal guard
    """Always raise: Supabase support was removed in favour of SQLite."""
    raise RuntimeError(
        "Supabase support was removed. MEDUSA-X stores all data in SQLite; "
        "no external database credentials are used."
    )
