"""Interactive device code authentication flow for Sunday."""

from __future__ import annotations

import asyncio
import webbrowser
from datetime import datetime, timedelta, timezone

from rich.console import Console

from nanobot.sunday.client import SundayClient
from nanobot.sunday.types import DeviceTokenResponse

console = Console()


async def device_code_flow(base_url: str) -> DeviceTokenResponse:
    """Run the device code auth flow interactively.

    Displays the user code, opens the browser to the verification URL,
    and polls until the user completes authentication.

    Returns the token response with access, refresh, and user info.
    """
    client = SundayClient(base_url=base_url)
    try:
        # Step 1: Request device code
        dc = await client.request_device_code()

        console.print()
        console.print("[bold cyan]Sunday Authentication[/bold cyan]")
        console.print()
        console.print(f"  Your code: [bold yellow]{dc.user_code}[/bold yellow]")
        console.print()
        console.print(f"  Open: [link={dc.verification_uri}?user_code={dc.user_code}]{dc.verification_uri}[/link]")
        console.print()

        # Try to open browser
        try:
            webbrowser.open(f"{dc.verification_uri}?user_code={dc.user_code}")
            console.print("  [dim]Browser opened. Complete sign-in there.[/dim]")
        except Exception:
            console.print("  [dim]Open the URL above in your browser to sign in.[/dim]")

        console.print()

        # Step 2: Poll for token
        with console.status("[dim]Waiting for authentication...[/dim]", spinner="dots"):
            deadline = asyncio.get_event_loop().time() + dc.expires_in
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(dc.interval)
                result = await client.poll_device_token(dc.device_code)
                if result is not None:
                    console.print("[green]✓[/green] Authenticated!")
                    return result

        raise TimeoutError("Device code expired. Please try again.")
    finally:
        await client.close()
