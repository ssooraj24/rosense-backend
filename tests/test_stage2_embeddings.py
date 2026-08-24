import pytest
import unittest
import math
from app.services.embedding_service import (
    bge_embedding_service,
    BGE_EMBEDDING_DIM,
    BGE_QUERY_PREFIX
)

class TestStage2Embeddings(unittest.TestCase):
    def setUp(self):
        self.service = bge_embedding_service

    def test_embedding_dimensions(self):
        """
        Verify that BGE embeddings are strictly 1024-dimensional vectors.
        """
        text = "SOC2 Type II compliance and AES-256 envelope encryption in memory."
        vec = self.service.embed_text(text)
        self.assertEqual(len(vec), BGE_EMBEDDING_DIM)
        self.assertEqual(len(vec), 1024)

    def test_l2_normalization(self):
        """
        Verify that embedding vectors are L2-normalized (length/magnitude ~ 1.0).
        """
        text = "Private Box hardware appliance testing scheduled for Friday."
        vec = self.service.embed_text(text)
        magnitude = math.sqrt(sum(x * x for x in vec))
        self.assertAlmostEqual(magnitude, 1.0, places=4)

    def test_query_prefix_application(self):
        """
        Verify that query prefix modifies the embedding appropriately for search retrieval.
        """
        query = "What is the timeline for hardware testing?"
        doc_vec = self.service.embed_text(query, is_query=False)
        query_vec = self.service.embed_text(query, is_query=True)

        self.assertEqual(len(query_vec), 1024)
        self.assertEqual(len(doc_vec), 1024)
        # Query prefix changes representation slightly to optimize cross-attention retrieval
        self.assertNotEqual(doc_vec, query_vec)

    def test_batch_embedding_consistency(self):
        """
        Verify batch embedding produces consistent 1024-dim vectors matching single calls.
        """
        texts = [
            "We have scheduled the 8GB VRAM swapping test with WhisperX and Mamba.",
            "Client compliance teams require zero data retention by external LLMs.",
            "Good morning everyone. Let's begin the review on the Q3 enterprise memory rollout."
        ]
        batch_vecs = self.service.embed_batch(texts)
        self.assertEqual(len(batch_vecs), 3)
        for vec in batch_vecs:
            self.assertEqual(len(vec), 1024)
            mag = math.sqrt(sum(x * x for x in vec))
            self.assertAlmostEqual(mag, 1.0, places=4)

    def test_semantic_cosine_similarity(self):
        """
        Verify cosine similarity is higher for semantically related sentences
        than for completely unrelated topics.
        """
        text_a = "AES-256 GCM envelope encryption secures data in RAM."
        text_b = "Cryptographic data security with encryption keys in memory."
        text_c = "Delicious pasta recipe with tomato and cheese sauce."

        vec_a = self.service.embed_text(text_a)
        vec_b = self.service.embed_text(text_b)
        vec_c = self.service.embed_text(text_c)

        sim_ab = self.service.compute_similarity(vec_a, vec_b)
        sim_ac = self.service.compute_similarity(vec_a, vec_c)

        # Related security texts should score higher than security vs cooking recipe
        self.assertGreater(sim_ab, sim_ac)
        self.assertGreaterEqual(sim_ab, 0.0)
        self.assertLessEqual(sim_ab, 1.0)
