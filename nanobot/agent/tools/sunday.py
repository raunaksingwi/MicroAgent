"""Sunday identity tool for managing passwords, inbox, and identity."""

from typing import Any

from nanobot.agent.tools.base import Tool


class SundayTool(Tool):
    """Tool for interacting with the agent's Sunday digital identity.

    Provides access to password management, email inbox, and identity
    information. All data is E2E encrypted transparently by the client.
    """

    def __init__(self, sunday_client):
        self._client = sunday_client

    @property
    def name(self) -> str:
        return "sunday"

    @property
    def description(self) -> str:
        return (
            "Manage your Sunday digital identity — passwords, email inbox, and identity info. "
            "All data is end-to-end encrypted.\n\n"
            "WORKFLOW for signing up for a new service:\n"
            "1. generate_password → get a secure random password\n"
            "2. create_password with the domain, generated password, and your Sunday email as username\n"
            "3. Use your Sunday email (from get_identity) to sign up on the website\n"
            "4. Check list_inbox for verification emails\n\n"
            "Actions: get_identity, get_master, list_emails, "
            "list_inbox, get_email, "
            "list_passwords, get_password, create_password, update_password, "
            "delete_password, generate_password."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "get_identity",
                        "get_master",
                        "list_emails",
                        "list_inbox",
                        "get_email",
                        "list_passwords",
                        "get_password",
                        "create_password",
                        "update_password",
                        "delete_password",
                        "generate_password",
                    ],
                    "description": "Action to perform",
                },
                "uuid": {
                    "type": "string",
                    "description": "UUID of the resource (for get/update/delete password)",
                },
                "message_id": {
                    "type": "integer",
                    "description": "Email message ID (for get_email)",
                },
                "domain": {
                    "type": "string",
                    "description": "Website domain e.g. 'github.com' (for create/update password)",
                },
                "username": {
                    "type": "string",
                    "description": "Username/email for the site (defaults to your Sunday email if omitted)",
                },
                "password": {
                    "type": "string",
                    "description": "Password value (for create/update password). Use generate_password first.",
                },
                "notes": {
                    "type": "string",
                    "description": "Notes (for create/update password)",
                },
                "length": {
                    "type": "integer",
                    "description": "Password length (for generate_password, default 16)",
                },
            },
            "required": ["action"],
        }

    async def execute(self, action: str, **kwargs: Any) -> str:
        try:
            if action == "get_identity":
                return await self._get_identity()
            elif action == "get_master":
                return await self._get_master()
            elif action == "list_emails":
                return await self._list_emails()
            elif action == "list_inbox":
                return await self._list_inbox()
            elif action == "get_email":
                return await self._get_email(kwargs.get("message_id"))
            elif action == "list_passwords":
                return await self._list_passwords()
            elif action == "get_password":
                return await self._get_password(kwargs.get("uuid"))
            elif action == "create_password":
                return await self._create_password(kwargs)
            elif action == "update_password":
                return await self._update_password(kwargs.get("uuid"), kwargs)
            elif action == "delete_password":
                return await self._delete_password(kwargs.get("uuid"))
            elif action == "generate_password":
                return await self._generate_password(kwargs.get("length", 16))
            return f"Unknown action: {action}"
        except Exception as e:
            return f"Error: {e}"

    async def _get_identity(self) -> str:
        identities = await self._client.list_identities()
        if not identities:
            return "No identities found."
        ident = identities[0]
        email_info = f", email: {ident.sunday_email}" if ident.sunday_email else ""
        return f"Identity: {ident.name} (uuid: {ident.uuid}{email_info})"

    async def _get_master(self) -> str:
        master = await self._client.get_master()
        return f"Master: {master.first_name} {master.last_name} ({master.email})"

    async def _list_emails(self) -> str:
        emails = await self._client.list_emails()
        if not emails:
            return "No email addresses provisioned."
        lines = []
        for e in emails:
            addr = e.get("email", "") if isinstance(e, dict) else getattr(e, "email", "")
            lines.append(f"- {addr}")
        return "Email addresses:\n" + "\n".join(lines)

    async def _list_inbox(self) -> str:
        messages = await self._client.list_inbox()
        if not messages:
            return "Inbox is empty."
        lines = []
        for m in messages[:20]:  # limit display
            read = "✓" if m.is_read else "●"
            lines.append(f"[{read}] {m.type}: {m.from_address} — {m.subject or m.body[:60]}")
        return f"Inbox ({len(messages)} messages):\n" + "\n".join(lines)

    async def _get_email(self, message_id: int | None) -> str:
        if not message_id:
            return "Error: message_id is required"
        msg = await self._client.get_email_message(message_id)
        return (
            f"From: {msg.from_email}\n"
            f"To: {msg.to_email}\n"
            f"Subject: {msg.subject}\n"
            f"Date: {msg.created_dt}\n"
            f"Read: {msg.is_read}\n\n"
            f"{msg.text_content}"
        )

    async def _list_passwords(self) -> str:
        passwords = await self._client.list_passwords()
        if not passwords:
            return "No saved passwords."
        lines = []
        for p in passwords:
            lines.append(f"- {p.domain}: {p.username} (uuid: {p.uuid})")
        return f"Passwords ({len(passwords)}):\n" + "\n".join(lines)

    async def _get_password(self, uuid: str | None) -> str:
        if not uuid:
            return "Error: uuid is required"
        p = await self._client.get_password(uuid)
        return (
            f"Domain: {p.domain}\n"
            f"Username: {p.username}\n"
            f"Password: {p.password}\n"
            f"Notes: {p.notes}"
        )

    async def _create_password(self, kwargs: dict) -> str:
        data = {
            k: v for k, v in kwargs.items()
            if k in ("domain", "username", "password", "notes") and v
        }
        if not data.get("domain"):
            return "Error: domain is required (e.g. 'github.com')"
        p = await self._client.create_password(data)
        return f"Password saved (uuid: {p.uuid}) for {p.domain}"

    async def _update_password(self, uuid: str | None, kwargs: dict) -> str:
        if not uuid:
            return "Error: uuid is required"
        data = {
            k: v for k, v in kwargs.items()
            if k in ("domain", "username", "password", "notes") and v
        }
        p = await self._client.update_password(uuid, data)
        return f"Password updated (uuid: {p.uuid})"

    async def _delete_password(self, uuid: str | None) -> str:
        if not uuid:
            return "Error: uuid is required"
        success = await self._client.delete_password(uuid)
        return "Password deleted." if success else "Failed to delete password."

    async def _generate_password(self, length: int = 16) -> str:
        result = await self._client.generate_password(length=length)
        return f"Generated password: {result.password}"
