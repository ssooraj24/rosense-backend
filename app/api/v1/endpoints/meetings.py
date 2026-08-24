import json
import uuid
from typing import Optional, List
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Header, status, UploadFile, File, Form, BackgroundTasks, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.supabase_client import get_supabase_client, get_supabase_admin_client
from app.services.audio_storage import (
    save_and_encrypt_uploaded_audio,
    get_audio_file_path,
    delete_stored_audio,
    read_decrypted_audio_stream
)
from app.core.crypto_vault import decrypt_audio_bytes
from app.services.whisper_pipeline import whisper_pipeline
from app.services.embedding_service import bge_embedding_service

router = APIRouter()

class UpdateSpeakerRequest(BaseModel):
    detected_name: Optional[str] = None
    role: Optional[str] = None
    color_code: Optional[str] = None

def get_current_user_and_org(authorization: Optional[str]):
    """
    Validates user session and extracts user and organization IDs.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Authorization token")
    
    token = authorization.split(" ")[1]
    admin_supabase = get_supabase_admin_client()
    user_supabase = get_supabase_client(user_jwt=token)
    
    try:
        user_res = user_supabase.auth.get_user(token)
        if not user_res.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")
        caller_user = user_res.user
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Authentication error: {str(e)}")

    # Resolve org_id
    org_id = None
    if caller_user.user_metadata and caller_user.user_metadata.get("org_id"):
        org_id = caller_user.user_metadata.get("org_id")
    
    if not org_id:
        try:
            p_res = admin_supabase.table("profiles").select("org_id").eq("id", caller_user.id).execute()
            if p_res.data and len(p_res.data) > 0 and p_res.data[0].get("org_id"):
                org_id = p_res.data[0].get("org_id")
        except Exception:
            pass

    if not org_id:
        try:
            r_res = admin_supabase.table("user_roles").select("org_id").eq("user_id", caller_user.id).execute()
            if r_res.data and len(r_res.data) > 0 and r_res.data[0].get("org_id"):
                org_id = r_res.data[0].get("org_id")
        except Exception:
            pass

    if not org_id:
        try:
            org_fallback = admin_supabase.table("organizations").select("id").limit(1).execute()
            if org_fallback.data and len(org_fallback.data) > 0:
                org_id = org_fallback.data[0].get("id")
        except Exception:
            pass

    if not org_id:
        raise HTTPException(status_code=400, detail="User is not associated with an active organization")

    return caller_user, org_id, token


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_meeting_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    department_id: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    language: Optional[str] = Form("en"),
    expected_speakers: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None)
):
    """
    Ingests audio file or in-browser live recording blob, performs AES-256-GCM Envelope
    Encryption, saves .enc ciphertext to tenant-scoped storage, creates database record,
    and queues Stage 1 WhisperX STT pipeline.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    meeting_id = str(uuid.uuid4())

    # 1. Encrypt and save audio to tenant-isolated disk storage (.enc)
    try:
        stored_path, orig_filename, file_size, mime_type, enc_dek_b64, iv_b64 = await save_and_encrypt_uploaded_audio(
            file=file,
            org_id=org_id,
            meeting_id=meeting_id
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to encrypt and store audio stream: {str(err)}")

    # Parse expected speakers list if supplied
    speakers_list = []
    if expected_speakers:
        try:
            if expected_speakers.startswith("["):
                speakers_list = json.loads(expected_speakers)
            else:
                speakers_list = [s.strip() for s in expected_speakers.split(",") if s.strip()]
        except Exception:
            speakers_list = [s.strip() for s in expected_speakers.split(",") if s.strip()]

    # 2. Insert meeting row in database with encrypted DEK and IV
    meeting_record = {
        "id": meeting_id,
        "org_id": org_id,
        "department_id": department_id if (department_id and len(department_id) > 10) else None,
        "created_by": caller_user.id,
        "title": title.strip(),
        "description": description.strip() if description else None,
        "audio_file_path": stored_path,
        "audio_file_name": orig_filename,
        "audio_mime_type": mime_type,
        "audio_size_bytes": file_size,
        "audio_duration_seconds": 0.0,
        "status": "queued",
        "language": language or "en",
        "metadata": {
            "encryption": "AES-256-GCM",
            "encrypted_dek": enc_dek_b64,
            "audio_iv": iv_b64
        },
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    try:
        insert_res = admin_supabase.table("meetings").insert(meeting_record).execute()
    except Exception as db_err:
        delete_stored_audio(stored_path)
        raise HTTPException(status_code=500, detail=f"Database record creation failed: {str(db_err)}")

    # 3. Trigger Stage 1 WhisperX STT Pipeline in background with RAM decryption
    background_tasks.add_task(
        whisper_pipeline.run_stage_1,
        meeting_id=meeting_id,
        org_id=org_id,
        audio_file_path=stored_path,
        encrypted_dek=enc_dek_b64,
        audio_iv=iv_b64,
        language=language or "en",
        expected_speakers=speakers_list
    )

    return {
        "status": "queued",
        "meeting_id": meeting_id,
        "title": title,
        "file_name": orig_filename,
        "file_size": file_size,
        "mime_type": mime_type,
        "encryption": "AES-256-GCM",
        "pipeline_stage": "stage1_whisperx_stt"
    }


@router.get("", response_model=List[dict])
async def list_meetings(
    department_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    authorization: Optional[str] = Header(None)
):
    """
    Retrieves all meetings within the tenant's organization with speaker counts.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    query = admin_supabase.table("meetings").select("*, departments(name, code), speakers(count)").eq("org_id", org_id).order("created_at", desc=True).limit(limit)

    if department_id:
        query = query.eq("department_id", department_id)
    if status_filter:
        query = query.eq("status", status_filter)

    res = query.execute()
    meetings = res.data or []

    if search and search.strip():
        term = search.lower().strip()
        meetings = [m for m in meetings if term in (m.get("title") or "").lower() or term in (m.get("description") or "").lower()]

    return meetings


@router.get("/{meeting_id}")
async def get_meeting_details(
    meeting_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Retrieves meeting metadata, speakers, and pipeline job status.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    meeting_res = admin_supabase.table("meetings").select("*, departments(name, code)").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not meeting_res.data or len(meeting_res.data) == 0:
        raise HTTPException(status_code=404, detail="Meeting not found or access denied")

    meeting = meeting_res.data[0]

    # Fetch speakers
    speakers_res = admin_supabase.table("speakers").select("*").eq("meeting_id", meeting_id).order("created_at").execute()
    
    # Fetch pipeline jobs
    jobs_res = admin_supabase.table("pipeline_jobs").select("*").eq("meeting_id", meeting_id).order("started_at", desc=True).limit(5).execute()

    return {
        "meeting": meeting,
        "speakers": speakers_res.data or [],
        "pipeline_jobs": jobs_res.data or []
    }


@router.get("/{meeting_id}/transcript")
async def get_meeting_transcript(
    meeting_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Retrieves Stage 1 diarized timestamp chunks with speaker associations.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    # Validate meeting exists for org
    m_check = admin_supabase.table("meetings").select("id, title, status, audio_duration_seconds").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_check.data:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting_info = m_check.data[0]

    # Fetch all transcript chunks in sequential order
    chunks_res = admin_supabase.table("transcript_chunks").select("*, speakers(*)").eq("meeting_id", meeting_id).order("sequence_index", desc=False).execute()
    
    # Fetch speakers
    speakers_res = admin_supabase.table("speakers").select("*").eq("meeting_id", meeting_id).execute()

    return {
        "meeting": meeting_info,
        "speakers": speakers_res.data or [],
        "chunks": chunks_res.data or [],
        "total_chunks": len(chunks_res.data or [])
    }


@router.get("/{meeting_id}/audio")
async def stream_meeting_audio(
    meeting_id: str,
    token: Optional[str] = None,
    authorization: Optional[str] = Header(None)
):
    """
    Securely streams the meeting audio file for in-browser playback.
    Decrypts AES-256-GCM ciphertext on-the-fly directly to RAM stream.
    """
    auth_header = authorization or (f"Bearer {token}" if token else None)
    caller_user, org_id, _ = get_current_user_and_org(auth_header)
    admin_supabase = get_supabase_admin_client()

    m_res = admin_supabase.table("meetings").select("audio_file_path, audio_mime_type, audio_file_name, metadata").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_res.data or not m_res.data[0].get("audio_file_path"):
        raise HTTPException(status_code=404, detail="Audio file not found")

    stored_path = m_res.data[0]["audio_file_path"]
    mime_type = m_res.data[0].get("audio_mime_type") or "audio/webm"
    filename = m_res.data[0].get("audio_file_name") or "meeting_audio.webm"
    meta = m_res.data[0].get("metadata") or {}

    file_path = get_audio_file_path(stored_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file storage inaccessible")

    # If encrypted with AES-256-GCM, decrypt in RAM
    if meta.get("encryption") == "AES-256-GCM" and meta.get("encrypted_dek") and meta.get("audio_iv"):
        try:
            with open(file_path, "rb") as f:
                enc_bytes = f.read()
            plain_bytes = decrypt_audio_bytes(
                encrypted_audio_bytes=enc_bytes,
                encrypted_dek_b64=meta["encrypted_dek"],
                iv_b64=meta["audio_iv"],
                org_id=org_id
            )
            return Response(
                content=plain_bytes,
                media_type=mime_type,
                headers={
                    "Content-Disposition": f'inline; filename="{filename}"',
                    "Content-Length": str(len(plain_bytes)),
                    "Accept-Ranges": "bytes"
                }
            )
        except Exception as dec_err:
            raise HTTPException(status_code=500, detail=f"Failed to decrypt audio stream: {str(dec_err)}")

    # Fallback to direct file response for unencrypted legacy audio
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=filename
    )


@router.patch("/{meeting_id}/speakers/{speaker_id}")
async def update_speaker(
    meeting_id: str,
    speaker_id: str,
    payload: UpdateSpeakerRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Updates speaker profile (name, role, or color code) across the meeting transcript.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    update_fields = {}
    if payload.detected_name is not None:
        update_fields["detected_name"] = payload.detected_name.strip()
    if payload.role is not None:
        update_fields["role"] = payload.role.strip()
    if payload.color_code is not None:
        update_fields["color_code"] = payload.color_code.strip()

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    res = admin_supabase.table("speakers").update(update_fields).eq("id", speaker_id).eq("meeting_id", meeting_id).eq("org_id", org_id).execute()
    return {"status": "success", "updated": res.data}


@router.post("/{meeting_id}/reprocess")
async def reprocess_stage_1(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
):
    """
    Re-runs Stage 1 WhisperX STT pipeline for a given meeting.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    m_res = admin_supabase.table("meetings").select("audio_file_path, language, metadata").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_res.data or not m_res.data[0].get("audio_file_path"):
        raise HTTPException(status_code=404, detail="Meeting audio not found")

    stored_path = m_res.data[0]["audio_file_path"]
    lang = m_res.data[0].get("language") or "en"
    meta = m_res.data[0].get("metadata") or {}

    # Clear previous chunks and speakers
    try:
        admin_supabase.table("transcript_chunks").delete().eq("meeting_id", meeting_id).execute()
        admin_supabase.table("speakers").delete().eq("meeting_id", meeting_id).execute()
    except Exception:
        pass

    background_tasks.add_task(
        whisper_pipeline.run_stage_1,
        meeting_id=meeting_id,
        org_id=org_id,
        audio_file_path=stored_path,
        encrypted_dek=meta.get("encrypted_dek"),
        audio_iv=meta.get("audio_iv"),
        language=lang
    )

    return {"status": "reprocessing_started", "meeting_id": meeting_id}


@router.delete("/{meeting_id}", status_code=status.HTTP_200_OK)
async def delete_meeting(
    meeting_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Deletes meeting record, audio file, and transcript chunks.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    m_res = admin_supabase.table("meetings").select("audio_file_path").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_res.data:
        raise HTTPException(status_code=404, detail="Meeting not found")

    stored_path = m_res.data[0].get("audio_file_path")
    if stored_path:
        delete_stored_audio(stored_path)

    admin_supabase.table("meetings").delete().eq("id", meeting_id).eq("org_id", org_id).execute()
    return {"status": "deleted", "meeting_id": meeting_id}


@router.post("/{meeting_id}/embed", status_code=status.HTTP_202_ACCEPTED)
async def trigger_stage2_embedding(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None)
):
    """
    Triggers Stage 2 Dense Vector Indexing (BGE-Large 1024-dim + pgvector) for a meeting.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    m_res = admin_supabase.table("meetings").select("id, status").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_res.data:
        raise HTTPException(status_code=404, detail="Meeting not found")

    background_tasks.add_task(
        bge_embedding_service.embed_and_index_meeting,
        meeting_id=meeting_id,
        org_id=org_id
    )

    return {
        "status": "stage2_indexing_queued",
        "meeting_id": meeting_id,
        "model": bge_embedding_service.model_name,
        "dimensions": bge_embedding_service.embedding_dim
    }


@router.get("/{meeting_id}/embeddings/status")
async def get_embeddings_status(
    meeting_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Retrieves Stage 2 dense vector embedding index status and chunk counts.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    m_res = admin_supabase.table("meetings").select("id, status").eq("id", meeting_id).eq("org_id", org_id).execute()
    if not m_res.data:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Count total chunks
    chunks_res = admin_supabase.table("transcript_chunks").select("id", count="exact").eq("meeting_id", meeting_id).execute()
    total_chunks = chunks_res.count or len(chunks_res.data or [])

    # Count embeddings
    embs_res = admin_supabase.table("transcript_embeddings").select("id", count="exact").eq("meeting_id", meeting_id).execute()
    indexed_chunks = embs_res.count or len(embs_res.data or [])

    is_complete = total_chunks > 0 and indexed_chunks >= total_chunks

    return {
        "meeting_id": meeting_id,
        "status": "completed" if is_complete else ("in_progress" if indexed_chunks > 0 else "pending"),
        "total_transcript_chunks": total_chunks,
        "indexed_embedding_chunks": indexed_chunks,
        "model": bge_embedding_service.model_name,
        "dimension": bge_embedding_service.embedding_dim,
        "is_indexed": is_complete
    }
