"""Lazy Supabase client configuration."""

from supabase import Client, create_client

from config import settings


def get_supabase_client() -> Client:
    """Create a Supabase client only when both credentials are configured."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SECRET_KEY before using Supabase.")
    return create_client(settings.supabase_url, settings.supabase_secret_key)
