"""Tests for the Sunday Email channel."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.sunday_email import SundayEmailChannel, _plain_to_html
from nanobot.sunday.types import EmailMessage, EmailThreadDetail


# ── helpers ────────────────────────────────────────────────────────────


def _make_email(
    id: int = 1,
    from_email: str = "master@example.com",
    to_email: str = "agent@sunday.so",
    subject: str = "Deploy v2",
    text_content: str = "Deploy version 2 to production",
    direction: str = "incoming",
    is_read: bool = False,
    message_id: str = "",
    thread_id: str = "<thread-1@example.com>",
    created_dt: str = "2026-02-15 10:00",
) -> EmailMessage:
    return EmailMessage(
        id=id,
        from_email=from_email,
        to_email=to_email,
        subject=subject,
        text_content=text_content,
        direction=direction,
        is_read=is_read,
        message_id=message_id,
        thread_id=thread_id,
        created_dt=created_dt,
    )


def _make_thread(
    thread_id: str = "<thread-1@example.com>",
    subject: str = "Deploy v2",
    messages: list[EmailMessage] | None = None,
) -> EmailThreadDetail:
    msgs = messages or []
    return EmailThreadDetail(
        thread_id=thread_id,
        subject=subject,
        message_count=len(msgs),
        messages=msgs,
    )


def _make_channel(
    master_email: str = "master@example.com",
    poll_interval_s: int = 60,
) -> tuple[SundayEmailChannel, AsyncMock]:
    bus = MessageBus()
    client = AsyncMock()
    ch = SundayEmailChannel(
        bus=bus,
        sunday_client=client,
        master_email=master_email,
        poll_interval_s=poll_interval_s,
    )
    return ch, client


# ── is_allowed ─────────────────────────────────────────────────────────


class TestIsAllowed:
    def test_master_accepted(self):
        ch, _ = _make_channel(master_email="master@example.com")
        assert ch.is_allowed("master@example.com") is True

    def test_other_rejected(self):
        ch, _ = _make_channel(master_email="master@example.com")
        assert ch.is_allowed("stranger@example.com") is False

    def test_case_insensitive(self):
        ch, _ = _make_channel(master_email="Master@Example.COM")
        assert ch.is_allowed("master@example.com") is True
        assert ch.is_allowed("MASTER@EXAMPLE.COM") is True

    def test_empty_master_rejects_all(self):
        ch, _ = _make_channel(master_email="")
        assert ch.is_allowed("anyone@example.com") is False

    def test_whitespace_stripped(self):
        ch, _ = _make_channel(master_email="  master@example.com  ")
        assert ch.is_allowed("master@example.com") is True


# ── _poll ──────────────────────────────────────────────────────────────


class TestPoll:
    @pytest.mark.asyncio
    async def test_fetches_unread_and_publishes_to_bus(self):
        ch, client = _make_channel()
        email = _make_email(id=1)
        thread = _make_thread(messages=[email])

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = thread
        client.mark_email_read.return_value = None

        await ch._poll()

        client.list_email_messages.assert_called_once_with(
            from_email="master@example.com",
            is_read=False,
            direction="incoming",
        )
        client.get_email_thread.assert_called_once_with("<thread-1@example.com>")
        client.mark_email_read.assert_called_once_with(1)
        assert 1 in ch._processed_ids
        assert ch.bus.inbound_size == 1

    @pytest.mark.asyncio
    async def test_deduplicates_by_email_id(self):
        ch, client = _make_channel()
        email = _make_email(id=42)
        thread = _make_thread(messages=[email])

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = thread
        client.mark_email_read.return_value = None

        await ch._poll()
        await ch._poll()

        # get_email_thread called only once despite two polls
        assert client.get_email_thread.call_count == 1
        assert ch.bus.inbound_size == 1

    @pytest.mark.asyncio
    async def test_marks_email_as_read(self):
        ch, client = _make_channel()
        email = _make_email(id=7)
        thread = _make_thread(messages=[email])

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = thread
        client.mark_email_read.return_value = None

        await ch._poll()

        client.mark_email_read.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_handles_thread_load_error_gracefully(self):
        ch, client = _make_channel()
        email = _make_email(id=3, text_content="Fallback content")

        client.list_email_messages.return_value = [email]
        client.get_email_thread.side_effect = Exception("API error")
        client.mark_email_read.return_value = None

        await ch._poll()

        # Should still process the email and publish to bus
        assert 3 in ch._processed_ids
        assert ch.bus.inbound_size == 1

    @pytest.mark.asyncio
    async def test_handles_mark_read_error_gracefully(self):
        ch, client = _make_channel()
        email = _make_email(id=5)
        thread = _make_thread(messages=[email])

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = thread
        client.mark_email_read.side_effect = Exception("API error")

        await ch._poll()

        # Should still mark as processed even if mark_read fails
        assert 5 in ch._processed_ids
        assert ch.bus.inbound_size == 1

    @pytest.mark.asyncio
    async def test_uses_thread_id_as_chat_id(self):
        ch, client = _make_channel()
        email = _make_email(id=1, thread_id="<custom-thread@mail.com>")
        thread = _make_thread(
            thread_id="<custom-thread@mail.com>",
            messages=[email],
        )

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = thread
        client.mark_email_read.return_value = None

        await ch._poll()

        msg = await ch.bus.consume_inbound()
        assert msg.chat_id == "<custom-thread@mail.com>"
        assert msg.channel == "sunday_email"

    @pytest.mark.asyncio
    async def test_fallback_thread_id_when_missing(self):
        ch, client = _make_channel()
        email = _make_email(id=99, thread_id="", message_id="<msg-99@mail.com>")

        client.list_email_messages.return_value = [email]
        client.get_email_thread.return_value = _make_thread(
            thread_id="<msg-99@mail.com>", messages=[email]
        )
        client.mark_email_read.return_value = None

        await ch._poll()

        msg = await ch.bus.consume_inbound()
        assert msg.chat_id == "<msg-99@mail.com>"

    @pytest.mark.asyncio
    async def test_handles_list_email_error_gracefully(self):
        """_poll should not crash when list_email_messages raises."""
        ch, client = _make_channel()
        client.list_email_messages.side_effect = Exception("network error")

        # Should raise (the start() loop catches this)
        with pytest.raises(Exception, match="network error"):
            await ch._poll()


# ── send ───────────────────────────────────────────────────────────────


class TestSend:
    @pytest.mark.asyncio
    async def test_replies_with_correct_id_and_subject(self):
        ch, client = _make_channel()
        ch._last_email_per_thread["<thread-1@example.com>"] = (10, "Deploy v2")
        client.reply_email.return_value = _make_email(id=11, direction="outgoing")

        await ch.send(OutboundMessage(
            channel="sunday_email",
            chat_id="<thread-1@example.com>",
            content="Deployed successfully.",
        ))

        client.reply_email.assert_called_once()
        call_args = client.reply_email.call_args
        assert call_args[0][0] == 10  # email_id
        assert "Deployed successfully." in call_args[0][1]  # html content
        assert call_args[0][2] == "Re: Deploy v2"  # subject

    @pytest.mark.asyncio
    async def test_wraps_content_in_html(self):
        ch, client = _make_channel()
        ch._last_email_per_thread["<t>"] = (1, "Test")
        client.reply_email.return_value = _make_email(id=2, direction="outgoing")

        await ch.send(OutboundMessage(
            channel="sunday_email",
            chat_id="<t>",
            content="Hello\nworld",
        ))

        html_arg = client.reply_email.call_args[0][1]
        assert "<p>" in html_arg
        assert "<br>" in html_arg

    @pytest.mark.asyncio
    async def test_handles_unknown_thread_gracefully(self):
        ch, client = _make_channel()

        # No crash when thread_id not in _last_email_per_thread
        await ch.send(OutboundMessage(
            channel="sunday_email",
            chat_id="<unknown-thread>",
            content="This should not crash.",
        ))

        client.reply_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_reply_api_error(self):
        ch, client = _make_channel()
        ch._last_email_per_thread["<t>"] = (1, "Test")
        client.reply_email.side_effect = Exception("server error")

        # Should not raise
        await ch.send(OutboundMessage(
            channel="sunday_email",
            chat_id="<t>",
            content="This should handle error gracefully.",
        ))

    @pytest.mark.asyncio
    async def test_does_not_double_prefix_re(self):
        ch, client = _make_channel()
        ch._last_email_per_thread["<t>"] = (1, "Re: Already prefixed")
        client.reply_email.return_value = _make_email(id=2, direction="outgoing")

        await ch.send(OutboundMessage(
            channel="sunday_email",
            chat_id="<t>",
            content="Reply.",
        ))

        subject_arg = client.reply_email.call_args[0][2]
        assert subject_arg == "Re: Already prefixed"
        assert not subject_arg.startswith("Re: Re:")


# ── thread content building ────────────────────────────────────────────


class TestBuildThreadContent:
    def test_single_message_no_thread(self):
        email = _make_email(text_content="Hello world")
        content = SundayEmailChannel._build_thread_content(email, None)
        assert content == "Hello world"

    def test_single_message_empty_thread(self):
        email = _make_email(text_content="Hello world")
        thread = _make_thread(messages=[])
        content = SundayEmailChannel._build_thread_content(email, thread)
        assert content == "Hello world"

    def test_includes_thread_history(self):
        msg1 = _make_email(id=1, text_content="Deploy v2", created_dt="2026-02-15 10:00")
        msg2 = _make_email(
            id=2, from_email="agent@sunday.so", text_content="Done.",
            direction="outgoing", created_dt="2026-02-15 10:05",
        )
        new_msg = _make_email(
            id=3, text_content="Also update docs",
            created_dt="2026-02-15 10:15",
        )
        thread = _make_thread(
            subject="Deploy v2",
            messages=[msg1, msg2, new_msg],
        )

        content = SundayEmailChannel._build_thread_content(new_msg, thread)

        assert 'Email thread: "Deploy v2"' in content
        assert "--- Thread History ---" in content
        assert "--- New Message ---" in content
        assert "Deploy v2" in content
        assert "(you)" in content  # outgoing message marked
        assert "Also update docs" in content

    def test_outgoing_messages_labeled_as_you(self):
        outgoing = _make_email(
            id=1, from_email="agent@sunday.so",
            text_content="I did it", direction="outgoing",
        )
        new_msg = _make_email(id=2, text_content="Great")
        thread = _make_thread(messages=[outgoing, new_msg])

        content = SundayEmailChannel._build_thread_content(new_msg, thread)
        assert "agent@sunday.so (you)" in content

    def test_falls_back_to_subject_when_no_text(self):
        email = _make_email(text_content="", subject="Important")
        content = SundayEmailChannel._build_thread_content(email, None)
        assert content == "Important"


# ── HTML conversion ────────────────────────────────────────────────────


class TestPlainToHtml:
    def test_single_paragraph(self):
        result = _plain_to_html("Hello world")
        assert result == "<p>Hello world</p>"

    def test_multiple_paragraphs(self):
        result = _plain_to_html("Paragraph 1\n\nParagraph 2")
        assert "<p>Paragraph 1</p>" in result
        assert "<p>Paragraph 2</p>" in result

    def test_preserves_line_breaks(self):
        result = _plain_to_html("Line 1\nLine 2")
        assert "<br>" in result

    def test_escapes_html_entities(self):
        result = _plain_to_html("Use <b> & 'quotes'")
        assert "&lt;b&gt;" in result
        assert "&amp;" in result


# ── lifecycle ──────────────────────────────────────────────────────────


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_skips_when_no_master_email(self):
        ch, client = _make_channel(master_email="")

        # start() should return immediately without polling
        await ch.start()

        assert ch.is_running is False
        client.list_email_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_sets_running_false(self):
        ch, _ = _make_channel()
        ch._running = True

        await ch.stop()

        assert ch.is_running is False

    def test_channel_name(self):
        ch, _ = _make_channel()
        assert ch.name == "sunday_email"

    @pytest.mark.asyncio
    async def test_start_polls_then_stops(self):
        """start() should poll and then respect _running = False."""
        ch, client = _make_channel(poll_interval_s=0)
        client.list_email_messages.return_value = []

        call_count = 0
        original_poll = ch._poll

        async def counting_poll():
            nonlocal call_count
            await original_poll()
            call_count += 1
            if call_count >= 2:
                ch._running = False

        ch._poll = counting_poll
        await ch.start()

        assert call_count >= 2
        assert ch.is_running is False
