"""Async HTTP client for the Sunday API with transparent E2E crypto."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Awaitable

import httpx
from loguru import logger

from nanobot.sunday.crypto import CryptoBox
import urllib.parse

from nanobot.sunday.types import (
    BindIdentityResponse,
    DeviceCodeResponse,
    DeviceTokenResponse,
    EmailMessage,
    EmailThreadDetail,
    EncryptionMeta,
    GeneratedPassword,
    Identity,
    InboxMessage,
    MasterInfo,
    PasswordEntry,
)

# Fields to encrypt/decrypt on password entries
_PW_ENCRYPTED_FIELDS = ("username", "password", "notes")


class SundayClient:
    """Async client for the Sunday REST API.

    Handles bearer-token auth, proactive + reactive token refresh, and
    transparent E2E encryption/decryption when a CryptoBox is provided.
    """

    def __init__(
        self,
        base_url: str,
        access_token: str = "",
        refresh_token: str = "",
        expires_at: str = "",
        crypto: CryptoBox | None = None,
        on_tokens_refreshed: Callable[[str, str, str], Awaitable[None]] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.crypto = crypto
        self.on_tokens_refreshed = on_tokens_refreshed
        self._http = httpx.AsyncClient(timeout=30.0)

    # ── helpers ───────────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    def _is_token_expired(self) -> bool:
        if not self.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(self.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= exp
        except ValueError:
            return False

    async def _ensure_token(self) -> None:
        """Proactively refresh if the access token is expired."""
        if self._is_token_expired() and self.refresh_token:
            await self._do_refresh()

    async def _do_refresh(self) -> None:
        """Refresh the access token using the refresh token."""
        try:
            resp = await self._http.post(
                f"{self.base_url}/api/token/refresh/",
                json={"refresh": self.refresh_token},
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access"]
            if "refresh" in data:
                self.refresh_token = data["refresh"]
            # Access tokens are 1h; store expiry as ISO
            self.expires_at = (
                datetime.now(timezone.utc).replace(microsecond=0)
                + timedelta(minutes=55)
            ).isoformat()
            if self.on_tokens_refreshed:
                await self.on_tokens_refreshed(
                    self.access_token, self.refresh_token, self.expires_at
                )
            logger.debug("Sunday token refreshed")
        except Exception as exc:
            logger.warning(f"Sunday token refresh failed: {exc}")

    async def _request(
        self, method: str, path: str, **kwargs: Any
    ) -> httpx.Response:
        """Make an authenticated request with auto-refresh on 401."""
        await self._ensure_token()
        url = f"{self.base_url}{path}"
        resp = await self._http.request(method, url, headers=self._headers(), **kwargs)
        if resp.status_code == 401 and self.refresh_token:
            await self._do_refresh()
            resp = await self._http.request(method, url, headers=self._headers(), **kwargs)
        return resp

    async def close(self) -> None:
        await self._http.aclose()

    # ── Auth (unauthenticated) ────────────────────────────────────────────

    async def request_device_code(self) -> DeviceCodeResponse:
        resp = await self._http.post(f"{self.base_url}/api/v1/auth/device/")
        resp.raise_for_status()
        return DeviceCodeResponse.model_validate(resp.json())

    async def poll_device_token(self, device_code: str) -> DeviceTokenResponse | None:
        """Poll once. Returns None if still pending, raises on error."""
        resp = await self._http.post(
            f"{self.base_url}/api/v1/auth/device/token/",
            json={"device_code": device_code},
        )
        if resp.status_code == 400:
            data = resp.json()
            if data.get("error") == "authorization_pending":
                return None
            raise RuntimeError(data.get("error_description", data.get("error", "Unknown error")))
        resp.raise_for_status()
        return DeviceTokenResponse.model_validate(resp.json())

    # ── Master ────────────────────────────────────────────────────────────

    async def get_master(self) -> MasterInfo:
        resp = await self._request("GET", "/api/v1/master/")
        resp.raise_for_status()
        return MasterInfo.model_validate(resp.json())

    # ── Encryption meta ───────────────────────────────────────────────────

    async def get_encryption_meta(self) -> EncryptionMeta:
        resp = await self._request("GET", "/api/v1/encryption/")
        resp.raise_for_status()
        return EncryptionMeta.model_validate(resp.json())

    async def set_encryption_meta(
        self, *, salt: str = "", verifier: str = "", public_key: str = ""
    ) -> EncryptionMeta:
        payload: dict[str, str] = {}
        if salt:
            payload["salt"] = salt
        if verifier:
            payload["verifier"] = verifier
        if public_key:
            payload["public_key"] = public_key
        resp = await self._request("PATCH", "/api/v1/encryption/", json=payload)
        resp.raise_for_status()
        return EncryptionMeta.model_validate(resp.json())

    # ── Identities ────────────────────────────────────────────────────────

    async def list_identities(self) -> list[Identity]:
        resp = await self._request("GET", "/api/v1/identities/")
        resp.raise_for_status()
        return [Identity.model_validate(item) for item in resp.json()]

    async def get_identity(self, uuid: str) -> Identity:
        resp = await self._request("GET", f"/api/v1/identities/{uuid}/")
        resp.raise_for_status()
        return Identity.model_validate(resp.json())

    async def create_identity(self, name: str) -> Identity:
        resp = await self._request("POST", "/api/v1/identities/", json={"name": name})
        resp.raise_for_status()
        return Identity.model_validate(resp.json())

    async def bind_identity(self, identity_uuid: str) -> BindIdentityResponse:
        resp = await self._request(
            "POST", "/api/v1/auth/bind-identity/", json={"identity": identity_uuid}
        )
        resp.raise_for_status()
        return BindIdentityResponse.model_validate(resp.json())

    # ── Emails ────────────────────────────────────────────────────────────

    async def list_emails(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/api/v1/email/")
        resp.raise_for_status()
        return resp.json()

    async def create_email(self, identity_uuid: str) -> dict[str, Any]:
        resp = await self._request(
            "POST", "/api/v1/email/", json={"identity": identity_uuid}
        )
        resp.raise_for_status()
        return resp.json()

    # ── Passwords (with transparent crypto) ───────────────────────────────

    def _encrypt_pw_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Encrypt password entry fields client-side before sending."""
        if not self.crypto:
            return data
        result = dict(data)
        for field in _PW_ENCRYPTED_FIELDS:
            if field in result and result[field] and not result[field].startswith("e2e::"):
                result[field] = self.crypto.encrypt(result[field])
        return result

    def _decrypt_pw_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Decrypt password entry fields client-side after receiving.

        The ``e2e::`` prefix on each field value determines whether it
        needs decryption — ``decrypt()`` returns non-prefixed strings as-is.
        """
        if not self.crypto:
            return data
        result = dict(data)
        for field in _PW_ENCRYPTED_FIELDS:
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = self.crypto.decrypt(result[field])
                except Exception:
                    pass  # leave as-is if decryption fails
        return result

    async def list_passwords(self) -> list[PasswordEntry]:
        resp = await self._request("GET", "/api/v1/passwords/")
        resp.raise_for_status()
        items = resp.json()
        return [PasswordEntry.model_validate(self._decrypt_pw_fields(item)) for item in items]

    async def get_password(self, uuid: str) -> PasswordEntry:
        resp = await self._request("GET", f"/api/v1/passwords/{uuid}/")
        resp.raise_for_status()
        return PasswordEntry.model_validate(self._decrypt_pw_fields(resp.json()))

    async def create_password(self, data: dict[str, Any]) -> PasswordEntry:
        payload = self._encrypt_pw_fields(data)
        resp = await self._request("POST", "/api/v1/passwords/", json=payload)
        resp.raise_for_status()
        return PasswordEntry.model_validate(self._decrypt_pw_fields(resp.json()))

    async def update_password(self, uuid: str, data: dict[str, Any]) -> PasswordEntry:
        payload = self._encrypt_pw_fields(data)
        resp = await self._request("PATCH", f"/api/v1/passwords/{uuid}/", json=payload)
        resp.raise_for_status()
        return PasswordEntry.model_validate(self._decrypt_pw_fields(resp.json()))

    async def delete_password(self, uuid: str) -> bool:
        resp = await self._request("DELETE", f"/api/v1/passwords/{uuid}/")
        return resp.status_code == 204

    async def generate_password(
        self, length: int = 16, **kwargs: Any
    ) -> GeneratedPassword:
        params: dict[str, Any] = {"length": length, **kwargs}
        resp = await self._request("GET", "/api/v1/passwords/generate-password/", params=params)
        resp.raise_for_status()
        return GeneratedPassword.model_validate(resp.json())

    # ── Inbox (with transparent crypto) ───────────────────────────────────

    def _decrypt_inbox_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Decrypt inbox message fields that may be e2e encrypted.

        The ``e2e::`` prefix on each field value determines whether it
        needs decryption — ``decrypt()`` returns non-prefixed strings as-is.
        """
        if not self.crypto:
            return data
        result = dict(data)
        for field in ("body", "subject", "text_content", "from_address", "to_address",
                       "from_email", "to_email"):
            if field in result and isinstance(result[field], str):
                try:
                    result[field] = self.crypto.decrypt(result[field])
                except Exception:
                    pass
        return result

    async def list_inbox(self, **params: Any) -> list[InboxMessage]:
        resp = await self._request("GET", "/api/v1/inbox/", params=params)
        resp.raise_for_status()
        items = resp.json()
        return [InboxMessage.model_validate(self._decrypt_inbox_fields(item)) for item in items]

    async def list_email_messages(self, **params: Any) -> list[EmailMessage]:
        resp = await self._request("GET", "/api/v1/email-messages/", params=params)
        resp.raise_for_status()
        items = resp.json()
        return [EmailMessage.model_validate(self._decrypt_inbox_fields(item)) for item in items]

    async def get_email_message(self, msg_id: int) -> EmailMessage:
        resp = await self._request("GET", f"/api/v1/email-messages/{msg_id}/")
        resp.raise_for_status()
        return EmailMessage.model_validate(self._decrypt_inbox_fields(resp.json()))

    async def get_email_thread(self, thread_id: str) -> EmailThreadDetail:
        """GET /api/v1/email-inbox/{thread_id}/ — full thread with all messages."""
        encoded = urllib.parse.quote(thread_id, safe="")
        resp = await self._request("GET", f"/api/v1/email-inbox/{encoded}/")
        resp.raise_for_status()
        data = resp.json()
        data["messages"] = [self._decrypt_inbox_fields(m) for m in data.get("messages", [])]
        return EmailThreadDetail.model_validate(data)

    async def reply_email(self, msg_id: int, content: str, subject: str) -> EmailMessage:
        """POST /api/v1/email-messages/{msg_id}/reply — reply to an email."""
        resp = await self._request(
            "POST", f"/api/v1/email-messages/{msg_id}/reply",
            json={"content": content, "subject": subject},
        )
        resp.raise_for_status()
        return EmailMessage.model_validate(resp.json())

    async def mark_email_read(self, msg_id: int) -> None:
        """PATCH /api/v1/email-messages/{msg_id}/ — mark as read."""
        resp = await self._request(
            "PATCH", f"/api/v1/email-messages/{msg_id}/",
            json={"is_read": True},
        )
        resp.raise_for_status()
