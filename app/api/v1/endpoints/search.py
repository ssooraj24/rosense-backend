import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Header, status, Depends
from pydantic import BaseModel, Field

from app.core.supabase_client import get_supabase_admin_client, get_supabase_client
from app.services.embedding_service import bge_embedding_service
from app.api.v1.endpoints.meetings import get_current_user_and_org

router = APIRouter()

class SemanticSearchRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Natural language search query")
    meeting_id: Optional[str] = Field(None, description="Optional meeting ID to restrict search to a single meeting")
    speaker_id: Optional[str] = Field(None, description="Optional speaker ID filter")
    min_similarity: float = Field(0.3, ge=0.0, le=1.0, description="Minimum cosine similarity threshold")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of results to return")
    include_context: bool = Field(True, description="Include adjacent transcript chunks for conversational context")

class SimilarChunksRequest(BaseModel):
    chunk_id: Optional[str] = Field(None, description="Transcript chunk ID to find similar occurrences for")
    text: Optional[str] = Field(None, description="Raw text excerpt to find similar chunks for")
    exclude_meeting_id: Optional[str] = Field(None, description="Optional meeting ID to exclude (e.g. current meeting)")
    limit: int = Field(5, ge=1, le=20, description="Maximum number of similar chunks")
    min_similarity: float = Field(0.4, ge=0.0, le=1.0, description="Minimum cosine similarity threshold")

class ChunkMatchResult(BaseModel):
    id: str
    meeting_id: str
    meeting_title: Optional[str] = None
    chunk_id: Optional[str] = None
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    speaker_label: str
    sequence_index: int
    start_time: float
    end_time: float
    text: str
    similarity_score: float
    context_window: Optional[Dict[str, Any]] = None

@router.post("/semantic", response_model=List[ChunkMatchResult])
async def semantic_search(
    payload: SemanticSearchRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Performs dense vector semantic search across meeting transcripts using BGE-Large
    embeddings and PostgreSQL pgvector cosine similarity matching.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    # 1. Generate 1024-dim BGE Query Embedding (with query prefix applied)
    query_vector = bge_embedding_service.embed_text(payload.query, is_query=True)

    # 2. Execute pgvector match query via RPC or Supabase query
    matches = []
    try:
        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": payload.min_similarity,
            "match_count": payload.limit,
            "filter_org_id": org_id,
            "filter_meeting_id": payload.meeting_id if payload.meeting_id else None,
            "filter_speaker_id": payload.speaker_id if payload.speaker_id else None
        }
        rpc_res = admin_supabase.rpc("match_transcript_embeddings", rpc_params).execute()
        if rpc_res.data:
            matches = rpc_res.data
    except Exception as rpc_err:
        # Fallback query if stored procedure is pending migration execution
        query_builder = admin_supabase.table("transcript_embeddings").select(
            "id, meeting_id, org_id, chunk_id, speaker_id, speaker_label, sequence_index, start_time, end_time, chunk_text, embedding"
        ).eq("org_id", org_id)

        if payload.meeting_id:
            query_builder = query_builder.eq("meeting_id", payload.meeting_id)
        if payload.speaker_id:
            query_builder = query_builder.eq("speaker_id", payload.speaker_id)

        res = query_builder.limit(100).execute()
        rows = res.data or []

        scored_rows = []
        for r in rows:
            emb = r.get("embedding")
            if emb:
                # If stored as vector string '[0.1, 0.2...]'
                if isinstance(emb, str):
                    try:
                        emb = [float(x.strip()) for x in emb.strip("[]").split(",") if x.strip()]
                    except Exception:
                        emb = []
                sim = bge_embedding_service.compute_similarity(query_vector, emb)
                if sim >= payload.min_similarity:
                    r_copy = dict(r)
                    r_copy["similarity"] = sim
                    scored_rows.append(r_copy)

        scored_rows.sort(key=lambda x: x["similarity"], reverse=True)
        matches = scored_rows[:payload.limit]

    if not matches:
        return []

    # 3. Enrich matches with Meeting Title, Speaker Names, and Context Windows
    meeting_ids = list({m["meeting_id"] for m in matches if m.get("meeting_id")})
    meetings_map = {}
    if meeting_ids:
        try:
            m_res = admin_supabase.table("meetings").select("id, title").in_("id", meeting_ids).execute()
            for m in (m_res.data or []):
                meetings_map[m["id"]] = m.get("title")
        except Exception:
            pass

    speaker_ids = list({m["speaker_id"] for m in matches if m.get("speaker_id")})
    speakers_map = {}
    if speaker_ids:
        try:
            s_res = admin_supabase.table("speakers").select("id, detected_name, speaker_label").in_("id", speaker_ids).execute()
            for s in (s_res.data or []):
                speakers_map[s["id"]] = s.get("detected_name") or s.get("speaker_label")
        except Exception:
            pass

    results = []
    for m in matches:
        meeting_id = m.get("meeting_id")
        seq_idx = m.get("sequence_index", 0)
        chunk_text = m.get("chunk_text") or m.get("text", "")
        sim_score = round(float(m.get("similarity", 0.0)), 4)

        context_window = None
        if payload.include_context and meeting_id:
            try:
                # Fetch preceding chunk (sequence_index - 1) and following chunk (sequence_index + 1)
                ctx_res = admin_supabase.table("transcript_chunks").select(
                    "sequence_index, speaker_label, text, start_time, end_time"
                ).eq("meeting_id", meeting_id).in_("sequence_index", [seq_idx - 1, seq_idx + 1]).execute()

                prev_chunk = None
                next_chunk = None
                for c in (ctx_res.data or []):
                    if c["sequence_index"] == seq_idx - 1:
                        prev_chunk = c
                    elif c["sequence_index"] == seq_idx + 1:
                        next_chunk = c

                context_window = {
                    "previous": prev_chunk,
                    "next": next_chunk
                }
            except Exception:
                context_window = None

        speaker_name = speakers_map.get(m.get("speaker_id")) or m.get("speaker_label")

        results.append(ChunkMatchResult(
            id=str(m.get("id", uuid.uuid4())),
            meeting_id=meeting_id,
            meeting_title=meetings_map.get(meeting_id, "Untitled Meeting"),
            chunk_id=m.get("chunk_id"),
            speaker_id=m.get("speaker_id"),
            speaker_name=speaker_name,
            speaker_label=m.get("speaker_label", "SPEAKER_00"),
            sequence_index=seq_idx,
            start_time=float(m.get("start_time", 0.0)),
            end_time=float(m.get("end_time", 0.0)),
            text=chunk_text,
            similarity_score=sim_score,
            context_window=context_window
        ))

    return results


@router.post("/similar-chunks", response_model=List[ChunkMatchResult])
async def find_similar_chunks(
    payload: SimilarChunksRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Finds semantically similar discussion points across the organization's past meetings
    given a chunk ID or reference text snippet.
    """
    caller_user, org_id, token = get_current_user_and_org(authorization)
    admin_supabase = get_supabase_admin_client()

    target_text = payload.text

    # If chunk_id is provided, retrieve its text
    if payload.chunk_id and not target_text:
        chunk_res = admin_supabase.table("transcript_chunks").select("text, meeting_id").eq("id", payload.chunk_id).execute()
        if chunk_res.data and len(chunk_res.data) > 0:
            target_text = chunk_res.data[0].get("text")
            if not payload.exclude_meeting_id:
                payload.exclude_meeting_id = chunk_res.data[0].get("meeting_id")

    if not target_text:
        raise HTTPException(status_code=400, detail="Must provide either chunk_id or text snippet")

    # Generate document embedding
    query_vector = bge_embedding_service.embed_text(target_text, is_query=True)

    # Search embeddings in org
    query_builder = admin_supabase.table("transcript_embeddings").select(
        "id, meeting_id, org_id, chunk_id, speaker_id, speaker_label, sequence_index, start_time, end_time, chunk_text, embedding"
    ).eq("org_id", org_id)

    if payload.exclude_meeting_id:
        query_builder = query_builder.neq("meeting_id", payload.exclude_meeting_id)

    res = query_builder.limit(100).execute()
    rows = res.data or []

    scored_rows = []
    for r in rows:
        emb = r.get("embedding")
        if emb:
            if isinstance(emb, str):
                try:
                    emb = [float(x.strip()) for x in emb.strip("[]").split(",") if x.strip()]
                except Exception:
                    emb = []
            sim = bge_embedding_service.compute_similarity(query_vector, emb)
            if sim >= payload.min_similarity:
                r_copy = dict(r)
                r_copy["similarity"] = sim
                scored_rows.append(r_copy)

    scored_rows.sort(key=lambda x: x["similarity"], reverse=True)
    top_matches = scored_rows[:payload.limit]

    # Fetch meeting titles
    meeting_ids = list({m["meeting_id"] for m in top_matches if m.get("meeting_id")})
    meetings_map = {}
    if meeting_ids:
        try:
            m_res = admin_supabase.table("meetings").select("id, title").in_("id", meeting_ids).execute()
            for m in (m_res.data or []):
                meetings_map[m["id"]] = m.get("title")
        except Exception:
            pass

    results = []
    for m in top_matches:
        results.append(ChunkMatchResult(
            id=str(m.get("id", uuid.uuid4())),
            meeting_id=m["meeting_id"],
            meeting_title=meetings_map.get(m["meeting_id"], "Past Meeting"),
            chunk_id=m.get("chunk_id"),
            speaker_id=m.get("speaker_id"),
            speaker_label=m.get("speaker_label", "SPEAKER_00"),
            sequence_index=m.get("sequence_index", 0),
            start_time=float(m.get("start_time", 0.0)),
            end_time=float(m.get("end_time", 0.0)),
            text=m.get("chunk_text", ""),
            similarity_score=round(float(m.get("similarity", 0.0)), 4)
        ))

    return results
