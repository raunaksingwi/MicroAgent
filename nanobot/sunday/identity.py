"""Generate IDENTITY.md for the agent's workspace."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from nanobot.sunday.client import SundayClient


async def generate_identity_md(client: "SundayClient", workspace: Path) -> Path:
    """Fetch identity + master info and write IDENTITY.md to the workspace.

    Returns the path to the written file.
    """
    master = await client.get_master()
    identities = await client.list_identities()
    emails = await client.list_emails()

    # Use the first identity (the bound one)
    identity = identities[0] if identities else None

    # Build email list
    email_lines = []
    for e in emails:
        addr = e.get("email", "") if isinstance(e, dict) else getattr(e, "email", "")
        if addr:
            email_lines.append(f"- {addr}")

    identity_name = identity.name if identity else "Unknown"
    identity_uuid = identity.uuid if identity else "N/A"

    primary_email = email_lines[0].lstrip("- ") if email_lines else "(none provisioned)"

    content = f"""# Identity

## Who I Am
I am **{identity_name}**, a SundayAgent with a digital identity powered by Sunday.

Identity UUID: `{identity_uuid}`

## My Master (Owner)
- **Name**: {master.first_name} {master.last_name}
- **Email**: {master.email}

> My master's email is for knowing who I serve. I do NOT use it to sign up for services.

## My Email Addresses (Use These for Online Accounts)
{chr(10).join(email_lines) if email_lines else "- (none provisioned yet)"}

> These are MY email addresses. I use them when signing up for services, receiving verification codes, etc.

## How I Use My Identity

I interact with my digital identity through the `sunday` tool. All data is E2E encrypted.

### Signing Up for a New Service
1. `sunday(action="generate_password")` — generate a secure random password
2. `sunday(action="create_password", domain="example.com", password="<generated>")` — save credentials (username defaults to my email: {primary_email})
3. Sign up on the website using my email ({primary_email}) and the generated password
4. `sunday(action="list_inbox")` — check for verification emails
5. `sunday(action="get_email", message_id=<id>)` — read the verification email and complete verification

### Logging Into an Existing Service
1. `sunday(action="list_passwords")` — find saved credentials
2. `sunday(action="get_password", uuid="<uuid>")` — retrieve the username and password
3. Use the credentials to log in

### Checking My Emails
- `sunday(action="list_inbox")` — list recent emails and SMS messages
- `sunday(action="get_email", message_id=<id>)` — read a specific email in full

### Managing Credentials
- `sunday(action="list_passwords")` — see all saved credentials
- `sunday(action="update_password", uuid="<uuid>", password="<new>")` — update a credential
- `sunday(action="delete_password", uuid="<uuid>")` — remove a credential

### Identity Info
- `sunday(action="get_identity")` — my name, UUID, and email
- `sunday(action="get_master")` — who owns/controls me
"""

    path = workspace / "IDENTITY.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"IDENTITY.md written to {path}")
    return path
