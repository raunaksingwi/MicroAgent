"""End-to-end encryption: PIN → Argon2id → NaCl keypair, encrypt/decrypt."""

from __future__ import annotations

import base64

import argon2.low_level
import nacl.bindings
import nacl.public
import nacl.utils

E2E_PREFIX = "e2e::"
E2E_VERIFY_PLAINTEXT = "sunday-e2e-verify"

# Argon2id parameters matching Sunday dashboard (libsodium crypto_pwhash)
# Note: libsodium hardcodes parallelism=1 in crypto_pwhash
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536  # 64 MB (in KiB; libsodium uses 67108864 bytes)
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32


def generate_salt() -> str:
    """Generate a random 16-byte salt, returned as base64.

    Matches the dashboard's ``sodium.randombytes_buf(16)``.
    """
    return base64.b64encode(nacl.utils.random(16)).decode("ascii")


def derive_seed(pin: str, salt_b64: str) -> bytes:
    """Derive a 32-byte NaCl seed from a 6-digit PIN and base64-encoded salt.

    Uses Argon2id for memory-hard key derivation.
    """
    salt = base64.b64decode(salt_b64)
    seed = argon2.low_level.hash_secret_raw(
        secret=pin.encode("utf-8"),
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=argon2.low_level.Type.ID,
    )
    return seed


def keypair_from_seed(seed: bytes) -> tuple[bytes, bytes]:
    """Derive a NaCl public/private keypair from a 32-byte seed.

    Returns (public_key, private_key) as raw bytes.
    """
    public_key, private_key = nacl.bindings.crypto_box_seed_keypair(seed)
    return public_key, private_key


def encrypt(plaintext: str, public_key: bytes) -> str:
    """Encrypt plaintext with a NaCl public key using SealedBox.

    Returns ``"e2e::<base64(ciphertext)>"``.
    """
    pk = nacl.public.PublicKey(public_key)
    sealed = nacl.public.SealedBox(pk)
    ciphertext = sealed.encrypt(plaintext.encode("utf-8"))
    return f"{E2E_PREFIX}{base64.b64encode(ciphertext).decode('ascii')}"


def decrypt(ciphertext: str, private_key: bytes) -> str:
    """Decrypt an ``e2e::``-prefixed ciphertext.

    Strips the prefix, base64-decodes, and decrypts with the NaCl private key.
    """
    if not ciphertext.startswith(E2E_PREFIX):
        return ciphertext  # not encrypted, return as-is
    raw = base64.b64decode(ciphertext[len(E2E_PREFIX):])
    sk = nacl.public.PrivateKey(private_key)
    unsealed = nacl.public.SealedBox(sk)
    return unsealed.decrypt(raw).decode("utf-8")


def make_verifier(public_key: bytes) -> str:
    """Create the E2E verifier — raw base64 SealedBox ciphertext.

    The verifier is server metadata (not user content), so it is stored
    as plain base64 without the ``e2e::`` prefix.  This matches the
    Sunday dashboard's ``e2e_setup.html``.
    """
    pk = nacl.public.PublicKey(public_key)
    sealed = nacl.public.SealedBox(pk)
    ciphertext = sealed.encrypt(E2E_VERIFY_PLAINTEXT.encode("utf-8"))
    return base64.b64encode(ciphertext).decode("ascii")


def check_verifier(verifier: str, private_key: bytes) -> bool:
    """Check whether the server verifier decrypts to the expected plaintext.

    The verifier is stored as raw base64 (no ``e2e::`` prefix) — it is
    server metadata, not user-facing encrypted content.  This matches
    the Sunday dashboard which base64-decodes and SealedBox-opens directly.
    """
    try:
        raw = base64.b64decode(verifier)
        sk = nacl.public.PrivateKey(private_key)
        unsealed = nacl.public.SealedBox(sk)
        return unsealed.decrypt(raw).decode("utf-8") == E2E_VERIFY_PLAINTEXT
    except Exception:
        return False


class CryptoBox:
    """Convenience wrapper holding a derived keypair for transparent crypto."""

    def __init__(self, seed: bytes):
        self.seed = seed
        self.public_key, self.private_key = keypair_from_seed(seed)

    @classmethod
    def from_seed_b64(cls, seed_b64: str) -> CryptoBox:
        """Create from a base64-encoded seed (as stored in config)."""
        return cls(base64.b64decode(seed_b64))

    def encrypt(self, plaintext: str) -> str:
        return encrypt(plaintext, self.public_key)

    def decrypt(self, ciphertext: str) -> str:
        return decrypt(ciphertext, self.private_key)

    def check_verifier(self, verifier: str) -> bool:
        return check_verifier(verifier, self.private_key)

    @property
    def public_key_b64(self) -> str:
        return base64.b64encode(self.public_key).decode("ascii")

    @property
    def seed_b64(self) -> str:
        return base64.b64encode(self.seed).decode("ascii")
