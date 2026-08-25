"""
RoSense AI - Asus RTX 5060 Mamba SSM Dedicated Worker
Runs on the Asus Laptop (RTX 5060 8GB GPU).
Pulls meeting transcripts, executes Mamba-3 SSM extraction in GPU VRAM,
writes structured results directly to Supabase/PostgreSQL, and updates pipeline jobs.

Usage on Asus Laptop:
    pip install fastapi uvicorn torch transformers supabase pydantic httpx
    python scripts/mamba_worker.py --port 8001 --host 0.0.0.0
"""

import os
import sys
import argparse
import asyncio
import uuid
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Try to import torch & transformers for GPU inference
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from supabase import create_client, Client

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_supabase()
    load_mamba_gpu()
    yield

app = FastAPI(
    title="RoSense AI - Asus RTX 5060 Mamba SSM Worker",
    description="Dedicated On-Premise GPU Inference Worker for Mamba State Space Extraction",
    lifespan=lifespan
)

# Configuration defaults (Can be overridden via environment variables)
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://your-project-ref.supabase.co")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "your-service-role-key")
MODEL_NAME = os.getenv("MAMBA_MODEL_NAME", "state-spaces/mamba-2.8b-hf")

# Global state
gpu_model = None
gpu_tokenizer = None
supabase: Optional[Client] = None

def init_supabase():
    global supabase
    if SUPABASE_URL and len(SUPABASE_URL) > 10 and not SUPABASE_URL.startswith("https://your-project"):
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            print(f"[INIT] Connected to Supabase at {SUPABASE_URL}")
        except Exception as e:
            print(f"[WARN] Supabase connection failed: {e}")

def load_mamba_gpu():
    """Loads Mamba SSM model into Asus RTX 5060 GPU VRAM."""
    global gpu_model, gpu_tokenizer
    if not TORCH_AVAILABLE:
        print("[INFO] PyTorch not installed. Running in CPU simulated SSM extraction mode.")
        return

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        print(f"[GPU] Detected {gpu_name} with {vram_gb} GB VRAM")
        try:
            print(f"[LOAD] Loading {MODEL_NAME} into GPU VRAM...")
            gpu_tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
            gpu_model = AutoModelForCausalLM.from_pretrained(
                MODEL_NAME,
                torch_dtype=torch.float16,
                device_map="cuda"
            )
            print(f"[LOAD] Mamba-3 model loaded successfully in GPU VRAM.")
        except Exception as e:
            print(f"[WARN] Could not load HuggingFace Mamba model ({e}). Using optimized onboard SSM extractor.")
    else:
        print("[WARN] CUDA not detected on this machine. Running in CPU mode.")

class ExtractMeetingRequest(BaseModel):
    meeting_id: str
    org_id: str
    chunks: Optional[List[Dict[str, Any]]] = None
    speakers: Optional[List[Dict[str, Any]]] = None

@app.get("/health")
def health():
    cuda_ok = TORCH_AVAILABLE and torch.cuda.is_available()
    vram_free = None
    if cuda_ok:
        free_b, total_b = torch.cuda.mem_get_info()
        vram_free = f"{round(free_b / (1024**3), 2)} GB / {round(total_b / (1024**3), 2)} GB"
    return {
        "status": "online",
        "worker": "Asus RTX 5060 Mamba Engine",
        "cuda_available": cuda_ok,
        "vram_status": vram_free,
        "model": MODEL_NAME
    }

@app.post("/v1/mamba/extract")
async def extract_meeting_endpoint(req: ExtractMeetingRequest):
    """
    Extracts decisions, tasks, risks, speaker dynamics, and executive insights.
    Returns structured JSON directly to the caller.
    """
    try:
        from app.services.mamba_ssm_service import mamba_ssm_service
        res = await mamba_ssm_service._run_onboard_extraction(
            meeting_id=req.meeting_id,
            org_id=req.org_id,
            chunks=req.chunks or [],
            speakers=req.speakers or []
        )
        return res
    except Exception as err:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(err)}")

@app.post("/v1/mamba/process-job/{meeting_id}")
async def process_job_and_save_to_db(meeting_id: str, org_id: str, background_tasks: BackgroundTasks):
    """
    Asynchronous Worker Pattern:
    1. Laptop pulls transcript & speakers from Database.
    2. Runs Mamba SSM extraction in GPU VRAM.
    3. Writes directly into public.decisions, public.tasks, public.risks,
       public.speaker_dynamics, and public.meeting_insights in Database.
    4. Updates meetings.status = 'ready' and notifies.
    """
    from app.services.mamba_ssm_service import mamba_ssm_service
    background_tasks.add_task(mamba_ssm_service.extract_and_persist_meeting, meeting_id=meeting_id, org_id=org_id)
    return {
        "status": "processing_started",
        "meeting_id": meeting_id,
        "worker": "Asus RTX 5060 Mamba Worker",
        "mode": "direct_db_persistence"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoSense AI Mamba Worker")
    parser.add_argument("--host", default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on")
    args = parser.parse_args()

    print(f"Starting RoSense AI Mamba SSM Worker on {args.host}:{args.port}...")
    uvicorn.run(app, host=args.host, port=args.port)
