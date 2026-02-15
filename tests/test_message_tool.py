"""Tests for the MessageTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from nanobot.agent.tools.message import MessageTool
from nanobot.bus.events import OutboundMessage


def _make_tool(
    default_channel: str = "sunday_email",
    default_chat_id: str = "<thread-1@example.com>",
    send_callback: AsyncMock | None = None,
) -> tuple[MessageTool, AsyncMock]:
    callback = send_callback or AsyncMock()
    tool = MessageTool(
        send_callback=callback,
        default_channel=default_channel,
        default_chat_id=default_chat_id,
    )
    return tool, callback


class TestExecuteCrossChannel:
    """Tests for cross-channel message sending."""

    @pytest.mark.asyncio
    async def test_sends_to_different_channel(self):
        tool, callback = _make_tool()
        result = await tool.execute(
            content="Cross-channel message",
            channel="telegram",
            chat_id="12345",
        )
        assert "Message sent" in result
        callback.assert_called_once()
        msg = callback.call_args[0][0]
        assert isinstance(msg, OutboundMessage)
        assert msg.channel == "telegram"
        assert msg.chat_id == "12345"
        assert msg.content == "Cross-channel message"

    @pytest.mark.asyncio
    async def test_sends_to_different_chat_id(self):
        tool, callback = _make_tool()
        result = await tool.execute(
            content="Different thread",
            chat_id="<other-thread@example.com>",
        )
        assert "Message sent" in result
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_to_default_channel(self):
        """With defaults set, sending without overrides uses the defaults."""
        tool, callback = _make_tool()
        result = await tool.execute(content="Hello")
        assert "Message sent" in result
        callback.assert_called_once()
        msg = callback.call_args[0][0]
        assert msg.channel == "sunday_email"
        assert msg.chat_id == "<thread-1@example.com>"

    @pytest.mark.asyncio
    async def test_error_when_no_channel_or_chat(self):
        """With no defaults and no explicit target, returns error."""
        tool = MessageTool()
        result = await tool.execute(content="Hello")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_error_when_no_callback(self):
        """Cross-channel send without a callback configured returns error."""
        tool = MessageTool()
        tool.set_context("ch1", "id1")
        result = await tool.execute(content="Hello", channel="ch2", chat_id="id2")
        assert "Error" in result

    @pytest.mark.asyncio
    async def test_handles_send_error(self):
        callback = AsyncMock(side_effect=Exception("network failure"))
        tool, _ = _make_tool(send_callback=callback)
        result = await tool.execute(
            content="Will fail",
            channel="telegram",
            chat_id="999",
        )
        assert "Error" in result
        assert "network failure" in result


class TestToolMetadata:
    def test_name(self):
        tool, _ = _make_tool()
        assert tool.name == "message"

    def test_parameters_schema(self):
        tool, _ = _make_tool()
        params = tool.parameters
        assert "content" in params["properties"]
        assert "content" in params["required"]

    def test_set_context(self):
        tool, _ = _make_tool()
        tool.set_context("discord", "guild-123")
        assert tool._default_channel == "discord"
        assert tool._default_chat_id == "guild-123"
