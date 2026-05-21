"""
Шифрування / розшифрування на сервері (транзитне).
AES-256-GCM з ключем із env ENCRYPTION_TRANSIT_KEY.
"""
import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _derive_key(passphrase: str) -> bytes:
    """Derive 256-bit key from passphrase using SHA-256."""
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def encrypt_data(plaintext: str, passphrase: str) -> str:
    """Encrypt plaintext → base64 string (nonce + ciphertext)."""
    key = _derive_key(passphrase)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_data(encrypted_b64: str, passphrase: str) -> str:
    """Decrypt base64 string (nonce + ciphertext) → plaintext."""
    key = _derive_key(passphrase)
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted_b64)
    nonce = raw[:12]
    ciphertext = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
