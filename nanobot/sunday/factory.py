"""Factory to create a SundayClient from nanobot config."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.sunday.client import SundayClient


def create_sunday_client(config) -> "SundayClient | None":
    """Create a SundayClient from the nanobot Config object.

    Returns None if Sunday is not configured (no tokens stored).
    Raises RuntimeError if SUNDAY_API_URL is not set but tokens exist.
    """
    from nanobot.sunday.client import SundayClient
    from nanobot.sunday.crypto import CryptoBox
    from nanobot.config.loader import save_config

    sunday = getattr(config, "sunday", None)
    if sunday is None or not sunday.access_token:
        return None

    base_url = os.environ.get("SUNDAY_API_URL")
    if not base_url:
        raise RuntimeError(
            "SUNDAY_API_URL environment variable is required when Sunday is configured. "
            "Set it to the Sunday API base URL (e.g. https://api.sunday.so)."
        )

    # Derive crypto box from stored seed
    crypto: CryptoBox | None = None
    if sunday.e2e_seed:
        try:
            crypto = CryptoBox.from_seed_b64(sunday.e2e_seed)
            logger.debug("Sunday E2E crypto loaded from stored seed")
        except Exception as exc:
            logger.warning(f"Failed to load Sunday E2E crypto: {exc}")

    # Token refresh callback to persist new tokens
    async def _on_tokens_refreshed(access: str, refresh: str, expires_at: str) -> None:
        try:
            from nanobot.config.loader import load_config, save_config
            cfg = load_config()
            cfg.sunday.access_token = access
            cfg.sunday.refresh_token = refresh
            cfg.sunday.expires_at = expires_at
            save_config(cfg)
            logger.debug("Sunday tokens persisted after refresh")
        except Exception as exc:
            logger.warning(f"Failed to persist refreshed Sunday tokens: {exc}")

    return SundayClient(
        base_url=base_url,
        access_token=sunday.access_token,
        refresh_token=sunday.refresh_token,
        expires_at=sunday.expires_at,
        crypto=crypto,
        on_tokens_refreshed=_on_tokens_refreshed,
    )
