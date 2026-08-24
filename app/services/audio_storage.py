import os
import uuid
import io
import shutil
from pathlib import Path
from typing import Tuple, Optional
from fastapi import UploadFile

from app.core.crypto_vault import encrypt_audio_envelope, decrypt_audio_bytes, decrypt_audio_to_ram

# Root storage directory for audio files
STORAGE_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "tenants"

# Supported audio extensions and MIME types
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac", ".aac", ".mp4"}
ALLOWED_MIME_PREFIXES = ("audio/", "video/webm", "video/mp4")

def ensure_tenant_audio_dir(org_id: str) -> Path:
    """
    Creates and returns the tenant-specific isolated audio storage directory.
    """
    tenant_dir = STORAGE_BASE_DIR / str(org_id) / "audio"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return tenant_dir

async def save_and_encrypt_uploaded_audio(
    file: UploadFile,
    org_id: str,
    meeting_id: str
) -> Tuple[str, str, int, str, str, str]:
    """
    Saves an uploaded audio file/blob securely using AES-256-GCM Envelope Encryption.
    Ciphertext is written to disk with .enc extension.
    
    Returns: (stored_file_path, original_filename, raw_file_size_bytes, mime_type, encrypted_dek_b64, iv_b64)
    """
    tenant_dir = ensure_tenant_audio_dir(org_id)
    
    original_filename = file.filename or "recording.webm"
    ext = Path(original_filename).suffix.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        if file.content_type and "webm" in file.content_type:
            ext = ".webm"
        elif file.content_type and "wav" in file.content_type:
            ext = ".wav"
        elif file.content_type and "mp3" in file.content_type:
            ext = ".mp3"
        else:
            ext = ".wav"
            
    # Read raw audio bytes
    raw_audio_bytes = await file.read()
    raw_file_size = len(raw_audio_bytes)
    
    # 1. AES-256-GCM Envelope Encryption
    ciphertext, enc_dek_b64, iv_b64 = encrypt_audio_envelope(raw_audio_bytes, org_id)
    
    # 2. Write strictly encrypted ciphertext to disk
    saved_filename = f"{meeting_id}.enc"
    target_path = tenant_dir / saved_filename
    
    with open(target_path, "wb") as f:
        f.write(ciphertext)
        
    mime_type = file.content_type or f"audio/{ext.lstrip('.')}"
    
    return str(target_path), original_filename, raw_file_size, mime_type, enc_dek_b64, iv_b64

def get_audio_file_path(stored_path: str) -> Optional[Path]:
    """
    Resolves stored audio file path and verifies existence.
    """
    p = Path(stored_path)
    if not p.is_absolute():
        p = STORAGE_BASE_DIR.parent / stored_path
    if p.exists() and p.is_file():
        return p
    return None

def read_decrypted_audio_stream(
    stored_path: str,
    encrypted_dek_b64: str,
    iv_b64: str,
    org_id: str
) -> io.BytesIO:
    """
    Decrypts stored .enc file directly in RAM and returns an in-memory stream buffer.
    """
    file_path = get_audio_file_path(stored_path)
    if not file_path or not file_path.exists():
        raise FileNotFoundError(f"Encrypted audio file not found: {stored_path}")
        
    return decrypt_audio_to_ram(file_path, encrypted_dek_b64, iv_b64, org_id)

def delete_stored_audio(stored_path: str) -> bool:
    """
    Deletes the encrypted audio file if it exists.
    """
    try:
        p = get_audio_file_path(stored_path)
        if p and p.exists():
            p.unlink()
            return True
    except Exception as e:
        print(f"[ERROR] Failed to delete encrypted audio file {stored_path}: {e}")
    return False
