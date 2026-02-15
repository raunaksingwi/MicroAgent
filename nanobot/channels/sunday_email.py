"""Sunday Email channel — master sends instructions via email threads."""

from __future__ import annotations

import asyncio
import html
from typing import Any

from loguru import logger

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.sunday.client import SundayClient
from nanobot.sunday.types import EmailMessage, EmailThreadDetail


class SundayEmailChannel(BaseChannel):
    """Channel that polls Sunday email API for master instructions.

    Each email thread becomes its own LLM conversation session
    (session_key = ``sunday_email:{thread_id}``).  Thread history is
    loaded from the API so the agent always has full context.
    """

    name = "sunday_email"

    def __init__(
        self,
        bus: MessageBus,
        sunday_client: SundayClient,
        master_email: str,
        poll_interval_s: int = 60,
    ) -> None:
        # BaseChannel expects (config, bus); we pass config=None since
        # this channel is not driven by config.channels.
        super().__init__(config=None, bus=bus)
        self.client = sunday_client
        self.master_email = master_email
        self.poll_interval_s = poll_interval_s
        self._processed_ids: set[int] = set()
        self._last_email_per_thread: dict[str, tuple[int, str]] = {}

    # ── lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        if not self.master_email:
            logger.info("SundayEmailChannel: no master_email configured, skipping")
            return
        self._running = True
        logger.info(
            f"SundayEmailChannel: polling every {self.poll_interval_s}s "
            f"for emails from {self.master_email}"
        )
        while self._running:
            try:
                await self._poll()
            except Exception:
                logger.exception("SundayEmailChannel: poll error")
            await asyncio.sleep(self.poll_interval_s)

    async def stop(self) -> None:
        self._running = False
        logger.info("SundayEmailChannel: stopped")

    # ── polling ────────────────────────────────────────────────────────

    async def _poll(self) -> None:
        emails = await self.client.list_email_messages(
            from_email=self.master_email,
            is_read=False,
            direction="incoming",
        )
        for email in emails:
            if email.id in self._processed_ids:
                continue
            await self._process_email(email)

    async def _process_email(self, email: EmailMessage) -> None:
        thread_id = email.thread_id or email.message_id or str(email.id)

        # Load full thread for context
        try:
            thread = await self.client.get_email_thread(thread_id)
        except Exception:
            logger.warning(
                f"SundayEmailChannel: could not load thread {thread_id}, "
                "using single message"
            )
            thread = None

        content = self._build_thread_content(email, thread)

        await self._handle_message(
            sender_id=email.from_email,
            chat_id=thread_id,
            content=content,
        )

        self._last_email_per_thread[thread_id] = (email.id, email.subject)

        try:
            await self.client.mark_email_read(email.id)
        except Exception:
            logger.warning(f"SundayEmailChannel: failed to mark email {email.id} as read")

        self._processed_ids.add(email.id)

    # ── send ───────────────────────────────────────────────────────────

    async def send(self, msg: OutboundMessage) -> None:
        thread_info = self._last_email_per_thread.get(msg.chat_id)
        if not thread_info:
            logger.warning(
                f"SundayEmailChannel: no tracked thread for chat_id={msg.chat_id}, "
                "cannot reply"
            )
            return
        email_id, subject = thread_info
        html_content = _plain_to_html(msg.content)
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        try:
            await self.client.reply_email(email_id, html_content, reply_subject)
        except Exception:
            logger.exception(
                f"SundayEmailChannel: failed to reply to email {email_id}"
            )

    # ── access control ─────────────────────────────────────────────────

    def is_allowed(self, sender_id: str) -> bool:
        if not self.master_email:
            return False
        return sender_id.strip().lower() == self.master_email.strip().lower()

    # ── thread context building ────────────────────────────────────────

    @staticmethod
    def _build_thread_content(
        new_email: EmailMessage,
        thread: EmailThreadDetail | None,
    ) -> str:
        if not thread or not thread.messages:
            return new_email.text_content or new_email.subject

        subject = thread.subject or new_email.subject
        total = thread.message_count or len(thread.messages)
        parts: list[str] = [f'Email thread: "{subject}" ({total} messages)']

        # Thread history (all messages except the new one)
        history_msgs = [m for m in thread.messages if m.id != new_email.id]
        if history_msgs:
            parts.append("")
            parts.append("--- Thread History ---")
            for m in history_msgs:
                label = m.from_email
                if m.direction == "outgoing":
                    label = f"{m.from_email} (you)"
                ts = m.created_dt[:16] if m.created_dt else ""
                body = m.text_content or m.subject
                parts.append(f"[{ts}] {label}:")
                parts.append(body)
                parts.append("")

        # New message
        parts.append("--- New Message ---")
        ts = new_email.created_dt[:16] if new_email.created_dt else ""
        parts.append(f"[{ts}] {new_email.from_email}:")
        parts.append(new_email.text_content or new_email.subject)

        return "\n".join(parts)


def _plain_to_html(text: str) -> str:
    """Wrap plain text in <p> tags, escaping HTML entities."""
    escaped = html.escape(text)
    paragraphs = escaped.split("\n\n")
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)
