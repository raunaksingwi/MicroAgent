"""Email check service — periodic inbox polling with sender-based trust."""

import asyncio
from typing import Any, Callable, Coroutine

from loguru import logger

from nanobot.sunday.client import SundayClient
from nanobot.sunday.email_processor import process_unread_emails

# Default: same cadence as heartbeat (30 minutes)
DEFAULT_EMAIL_INTERVAL_S = 30 * 60


class EmailService:
    """
    Periodic service that checks the Sunday inbox for unread emails.

    Follows the same start/stop/loop pattern as HeartbeatService.
    Sender trust classification happens in Python — never delegated to the LLM.
    """

    def __init__(
        self,
        client: SundayClient,
        master_email: str,
        on_email: Callable[[str], Coroutine[Any, Any, str]],
        interval_s: int = DEFAULT_EMAIL_INTERVAL_S,
        enabled: bool = True,
    ):
        self.client = client
        self.master_email = master_email
        self.on_email = on_email
        self.interval_s = interval_s
        self.enabled = enabled
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the email check service."""
        if not self.enabled:
            logger.info("Email service disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Email service started (every {self.interval_s}s)")

    def stop(self) -> None:
        """Stop the email check service."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _run_loop(self) -> None:
        """Main email check loop."""
        while self._running:
            try:
                await asyncio.sleep(self.interval_s)
                if self._running:
                    await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Email service error: {e}")

    async def _tick(self) -> None:
        """Execute a single email check."""
        await process_unread_emails(
            client=self.client,
            master_email=self.master_email,
            on_email=self.on_email,
        )
