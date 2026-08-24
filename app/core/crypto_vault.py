import os
import io
import base64
from typing import Tuple, Union, Optional
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

def get_vault_kek(org_id: Optional[str] = None) -> bytes:
    """
    Retrieves the 256-bit Key Encryption Key (KEK) for the tenant.
    Reads from ROSENSE_VAULT_KEK or falls back to system master key.
    """
    kek_b64 = settings.ROSENSE_VAULT_KEK
    try:
        kek = base64.b64decode(kek_b64)
        if len(kek) != 32:
            # Pad or derive 32 bytes if not exact
            kek = kek.ljust(32, b'\0')[:32]
        return kek
    except Exception:
        # Fallback SHA256-derived 32-byte key
        import hashlib
        return hashlib.sha256(kek_b64.encode()).digest()

def encrypt_audio_envelope(
    plain_audio_bytes: bytes,
    org_id: Optional[str] = None
) -> Tuple[bytes, str, str]:
    """
    AES-256-GCM Envelope Encryption:
    1. Generates a cryptographically random 256-bit DEK (Data Encryption Key).
    2. Generates a 96-bit (12-byte) unique IV / Nonce.
    3. Encrypts audio payload using AESGCM(DEK).
    4. Encrypts DEK using AESGCM(KEK).
    
    Returns: (encrypted_audio_bytes, base64_encrypted_dek, base64_iv)
    """
    kek = get_vault_kek(org_id)
    
    # 1. Generate unique 256-bit DEK & 12-byte IV
    dek = AESGCM.generate_key(bit_length=256)
    iv = os.urandom(12)
    
    # 2. Encrypt audio payload with DEK
    aesgcm_dek = AESGCM(dek)
    ciphertext = aesgcm_dek.encrypt(iv, plain_audio_bytes, None)
    
    # 3. Encrypt DEK with KEK (Envelope)
    aesgcm_kek = AESGCM(kek)
    encrypted_dek = aesgcm_kek.encrypt(iv, dek, None)
    
    enc_dek_b64 = base64.b64encode(encrypted_dek).decode("utf-8")
    iv_b64 = base64.b64encode(iv).decode("utf-8")
    
    return ciphertext, enc_dek_b64, iv_b64

def decrypt_dek_with_kek(
    encrypted_dek_b64: str,
    iv_b64: str,
    org_id: Optional[str] = None
) -> bytes:
    """
    Decrypts the envelope-encrypted DEK back into raw 256-bit key in RAM.
    """
    kek = get_vault_kek(org_id)
    encrypted_dek = base64.b64decode(encrypted_dek_b64)
    iv = base64.b64decode(iv_b64)
    
    aesgcm_kek = AESGCM(kek)
    plain_dek = aesgcm_kek.decrypt(iv, encrypted_dek, None)
    return plain_dek

def decrypt_audio_bytes(
    encrypted_audio_bytes: bytes,
    encrypted_dek_b64: str,
    iv_b64: str,
    org_id: Optional[str] = None
) -> bytes:
    """
    Decrypts AES-256-GCM ciphertext bytes into raw audio bytes in RAM.
    """
    plain_dek = decrypt_dek_with_kek(encrypted_dek_b64, iv_b64, org_id)
    iv = base64.b64decode(iv_b64)
    
    aesgcm_dek = AESGCM(plain_dek)
    plain_audio = aesgcm_dek.decrypt(iv, encrypted_audio_bytes, None)
    return plain_audio

def decrypt_audio_to_ram(
    enc_file_path: Union[str, Path],
    encrypted_dek_b64: str,
    iv_b64: str,
    org_id: Optional[str] = None
) -> io.BytesIO:
    """
    Reads .enc ciphertext from disk and decrypts directly into an in-memory
    io.BytesIO stream for WhisperX processing. Plaintext never touches disk.
    """
    p = Path(enc_file_path)
    with open(p, "rb") as f:
        enc_bytes = f.read()
        
    plain_bytes = decrypt_audio_bytes(enc_bytes, encrypted_dek_b64, iv_b64, org_id)
    return io.BytesIO(plain_bytes)
