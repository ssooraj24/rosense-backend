"""
RoSense AI - Stage 3 Mamba SSM Extraction Test Suite
Tests Stage 3 Mamba SSM structured extraction:
- Decisions & Rationale
- Tasks & Commitments
- Risks & Objections
- Speaker Dynamics & Mood Map
- Meeting Executive Insights & Health Scores
"""

import os
import sys
import uuid
import json
import asyncio
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.mamba_ssm_service import mamba_ssm_service

async def test_stage3_mamba_extraction():
    print("================================================================")
    print("   RoSense AI - Stage 3 Mamba SSM Extraction Verification")
    print("================================================================")

    # Sample Stage 1 Diarized Meeting Chunks
    sample_speakers = [
        {"id": str(uuid.uuid4()), "speaker_label": "SPEAKER_00", "detected_name": "Rahul Sharma", "role": "Engineering Lead"},
        {"id": str(uuid.uuid4()), "speaker_label": "SPEAKER_01", "detected_name": "Sarah Jenkins", "role": "Product Partner"},
        {"id": str(uuid.uuid4()), "speaker_label": "SPEAKER_02", "detected_name": "Amit Patel", "role": "VP Operations"}
    ]

    sample_chunks = [
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_00",
            "start_time": 0.0,
            "end_time": 8.5,
            "text": "Good morning everyone. Let's begin the review on the Q3 enterprise memory rollout and security architecture."
        },
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_01",
            "start_time": 8.8,
            "end_time": 19.2,
            "text": "Thanks Rahul. On the product side, client compliance teams from Tier 1 law firms require full row-level isolation and zero data retention by external LLMs."
        },
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_00",
            "start_time": 19.8,
            "end_time": 34.0,
            "text": "Understood. That's why Stage 1 WhisperX STT and Stage 3 Mamba SSM run entirely within the tenant vault. All audio and vector embeddings remain strictly on-premises."
        },
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_02",
            "start_time": 34.5,
            "end_time": 48.0,
            "text": "That addresses our SOC2 Type II compliance requirement directly. What is our timeline for the on-premise Private Box hardware appliance testing?"
        },
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_00",
            "start_time": 48.6,
            "end_time": 62.0,
            "text": "We have scheduled the 8GB VRAM swapping test with WhisperX and Mamba-3 2.8B for this Friday. All benchmark reports will be published to the leadership dashboard."
        },
        {
            "id": str(uuid.uuid4()),
            "speaker_label": "SPEAKER_01",
            "start_time": 62.5,
            "end_time": 75.0,
            "text": "Excellent. I will notify the client SPOCs that Stage 1 STT transcription with millisecond word alignment is now operational in the portal."
        }
    ]

    meeting_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    print(f"\n1. Ingesting {len(sample_chunks)} transcript chunks across {len(sample_speakers)} speakers...")
    
    # Run Stage 3 extraction
    extracted = await mamba_ssm_service._run_onboard_extraction(
        meeting_id=meeting_id,
        org_id=org_id,
        chunks=sample_chunks,
        speakers=sample_speakers
    )

    # 1. Verify Decisions
    decisions = extracted.get("decisions", [])
    print(f"\n[DECISIONS] Extracted {len(decisions)} decisions:")
    for d in decisions:
        print(f"  * [{d.get('speaker_label')}] {d.get('text')} (Confidence: {d.get('confidence')})")
        print(f"    Reason: {d.get('reason')}")
    assert len(decisions) > 0, "Expected at least 1 decision extracted"

    # 2. Verify Tasks
    tasks = extracted.get("tasks", [])
    print(f"\n[TASKS] Extracted {len(tasks)} action items:")
    for t in tasks:
        print(f"  * [{t.get('priority').upper()}] {t.get('text')} -> Assignee: {t.get('assignee_name')} (Due: {t.get('due_timeframe')})")
    assert len(tasks) > 0, "Expected at least 1 task extracted"

    # 3. Verify Risks
    risks = extracted.get("risks", [])
    print(f"\n[RISKS & OBJECTIONS] Extracted {len(risks)} risks:")
    for r in risks:
        print(f"  * [{r.get('severity').upper()}] {r.get('text')} (Status: {r.get('status')})")
        print(f"    Mitigation: {r.get('mitigation')}")
    assert len(risks) > 0, "Expected at least 1 risk extracted"

    # 4. Verify Speaker Dynamics
    dynamics = extracted.get("speaker_dynamics", [])
    print(f"\n[SPEAKER DYNAMICS & MOOD MAP] Extracted {len(dynamics)} speaker profiles:")
    for dy in dynamics:
        print(f"  * {dy.get('speaker_label')}: Sentiment={dy.get('sentiment')}, Emotion={dy.get('dominant_emotion')}, Intensity={dy.get('intensity')}/10, Concern={dy.get('concern_level')}, Stance={dy.get('agreement_stance')}")
        print(f"    Speaking Share: {dy.get('speaking_share_pct')}%")
    assert len(dynamics) == len(sample_speakers), "Expected dynamics for all speakers"

    # 5. Verify Meeting Insights & Health Score
    insights = extracted.get("insights", {})
    print(f"\n[EXECUTIVE INSIGHTS & MEETING HEALTH]")
    print(f"  * Health Rating: {insights.get('meeting_health_rating')}")
    print(f"  * Decision Quality Score: {insights.get('decision_quality_score')}%")
    print(f"  * Alignment Score: {insights.get('alignment_score')}%")
    print(f"  * Risk Index: {insights.get('risk_index')}%")
    print(f"  * Executive Summary: {insights.get('executive_summary')[:120]}...")
    assert "executive_summary" in insights, "Expected executive summary"

    print("\n================================================================")
    print("   Stage 3 Mamba SSM Extraction: ALL ASSERTIONS PASSED!")
    print("================================================================")

if __name__ == "__main__":
    asyncio.run(test_stage3_mamba_extraction())
