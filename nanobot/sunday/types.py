"""Pydantic models for Sunday API responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────

class DeviceCodeResponse(BaseModel):
    """Response from POST /api/v1/auth/device/."""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class SundayUser(BaseModel):
    """User info returned in device token response."""
    id: int
    email: str
    first_name: str = ""
    last_name: str = ""


class DeviceTokenResponse(BaseModel):
    """Successful response from POST /api/v1/auth/device/token/."""
    access: str
    refresh: str
    user: SundayUser


# ── Master ────────────────────────────────────────────────────────────────

class MasterInfo(BaseModel):
    """Response from GET /api/v1/master/."""
    first_name: str = ""
    last_name: str = ""
    email: str = ""


# ── Identity ──────────────────────────────────────────────────────────────

class SundayEmail(BaseModel):
    """A Sunday-provisioned email address."""
    id: int = 0
    email: str = ""
    uuid: str = ""


class SundayPhone(BaseModel):
    """A Sunday-provisioned phone number."""
    id: int = 0
    phone_number: str = ""
    uuid: str = ""


class Identity(BaseModel):
    """An identity grouping email + phone."""
    uuid: str
    name: str = ""
    sunday_email: str | None = None
    sunday_phone: str | None = None
    created_dt: str = ""
    updated_dt: str = ""


# ── Passwords ─────────────────────────────────────────────────────────────

class PasswordEntry(BaseModel):
    """A stored credential."""
    uuid: str = ""
    domain: str = ""
    username: str = ""
    password: str = ""
    notes: str = ""
    identity: str = ""  # identity UUID
    created_dt: str = ""
    updated_dt: str = ""


class GeneratedPassword(BaseModel):
    """Response from generate-password endpoint."""
    password: str


# ── Inbox ─────────────────────────────────────────────────────────────────

class InboxMessage(BaseModel):
    """Unified inbox message (SMS or email)."""
    id: int
    type: str  # "sms" or "email"
    from_address: str = ""
    to_address: str = ""
    subject: str = ""
    body: str = ""
    direction: str = ""
    is_read: bool = False
    created_dt: str = ""


class EmailMessage(BaseModel):
    """An email message."""
    id: int
    from_email: str = ""
    to_email: str = ""
    cc: str = ""
    subject: str = ""
    text_content: str = ""
    html_content: str = ""
    direction: str = ""       # "incoming" or "outgoing"
    is_read: bool = False
    message_id: str = ""      # RFC 2822 Message-ID
    in_reply_to: str = ""
    references: str = ""
    thread_id: str = ""       # Root message ID for grouping
    created_dt: str = ""


class EmailThread(BaseModel):
    """Thread summary from GET /api/v1/email-inbox/."""
    thread_id: str
    subject: str = ""
    preview: str = ""
    from_email: str = ""
    message_count: int = 0
    unread_count: int = 0
    latest_message_dt: str = ""


class EmailThreadDetail(BaseModel):
    """Full thread from GET /api/v1/email-inbox/{thread_id}/."""
    thread_id: str
    subject: str = ""
    message_count: int = 0
    messages: list[EmailMessage] = []


# ── Encryption ────────────────────────────────────────────────────────────

class EncryptionMeta(BaseModel):
    """Server-stored encryption metadata."""
    id: int = 0
    user_id: int = 0
    salt: str = ""
    verifier: str = ""
    public_key: str = ""
    managed_master_key: str | None = None
    created_dt: str = ""
    updated_dt: str = ""


# ── Bind Identity ─────────────────────────────────────────────────────────

class BindIdentityResponse(BaseModel):
    """Response from POST /api/v1/auth/bind-identity/."""
    access: str
    refresh: str
