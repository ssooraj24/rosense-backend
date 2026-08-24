import pytest
import unittest
import asyncio
from pathlib import Path
from app.services.whisper_pipeline import whisper_pipeline
from app.services.audio_storage import get_audio_file_path, ensure_tenant_audio_dir

class TestStage1Pipeline(unittest.IsolatedAsyncioTestCase):
    async def test_builtin_stt_transcription(self):
        """
        Tests Stage 1 STT processor chunk generation, speaker diarization,
        and millisecond alignment structure.
        """
        chunks, speakers, duration = await whisper_pipeline._run_builtin_stt_processor(
            audio_file_path="mock_audio.webm",
            language="en",
            expected_speakers=["Rahul Sharma (Tech Lead)", "Sarah Jenkins (Partner)"]
        )

        self.assertGreater(len(chunks), 0)
        self.assertGreater(len(speakers), 0)
        self.assertGreater(duration, 0)

        # Check speaker properties
        self.assertEqual(speakers[0]["name"], "Rahul Sharma")
        self.assertEqual(speakers[0]["role"], "Tech Lead")

        # Check chunk structure
        first_chunk = chunks[0]
        self.assertIn("speaker_label", first_chunk)
        self.assertIn("start_time", first_chunk)
        self.assertIn("end_time", first_chunk)
        self.assertIn("text", first_chunk)
        self.assertIn("confidence", first_chunk)
        self.assertGreaterEqual(first_chunk["confidence"], 0.9)

    def test_audio_storage_directory_creation(self):
        """
        Tests tenant-isolated directory creation.
        """
        tenant_dir = ensure_tenant_audio_dir("tenant_test_123")
        self.assertTrue(tenant_dir.exists())
        self.assertTrue(tenant_dir.is_dir())
