import os
import uuid
import shutil
from pathlib import Path
from typing import Tuple, Optional
from fastapi import UploadFile

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

async def save_uploaded_audio(
    file: UploadFile,
    org_id: str,
    meeting_id: str
) -> Tuple[str, str, int, str]:
    """
    Saves an uploaded audio file/blob securely into tenant-scoped storage.
    Returns: (relative_file_path, original_filename, file_size_bytes, mime_type)
    """
    tenant_dir = ensure_tenant_audio_dir(org_id)
    
    original_filename = file.filename or "recording.webm"
    ext = Path(original_filename).suffix.lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        # Default to .webm for browser recordings or .wav
        if file.content_type and "webm" in file.content_type:
            ext = ".webm"
        elif file.content_type and "wav" in file.content_type:
            ext = ".wav"
        elif file.content_type and "mp3" in file.content_type:
            ext = ".mp3"
        else:
            ext = ".wav"
            
    saved_filename = f"{meeting_id}{ext}"
    target_path = tenant_dir / saved_filename
    
    file_size = 0
    # Stream content to disk
    with open(target_path, "wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024) # 1MB chunks
            if not chunk:
                break
            buffer.write(chunk)
            file_size += len(chunk)
            
    # Reset file pointer if needed
    await file.seek(0)
    
    # Store relative path from backend root for portability
    rel_path = str(target_path.relative_to(STORAGE_BASE_DIR.parent))
    mime_type = file.content_type or f"audio/{ext.lstrip('.')}"
    
    return str(target_path), original_filename, file_size, mime_type

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

def delete_stored_audio(stored_path: str) -> bool:
    """
    Deletes the audio file if it exists.
    """
    try:
        p = get_audio_file_path(stored_path)
        if p and p.exists():
            p.unlink()
            return True
    except Exception as e:
        print(f"[ERROR] Failed to delete audio file {stored_path}: {e}")
    return False
