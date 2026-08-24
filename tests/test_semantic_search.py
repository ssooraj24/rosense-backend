import pytest
import unittest
from app.services.embedding_service import bge_embedding_service
from app.api.v1.endpoints.search import SemanticSearchRequest, SimilarChunksRequest

class TestSemanticSearch(unittest.TestCase):
    def setUp(self):
        self.service = bge_embedding_service

    def test_semantic_search_request_validation(self):
        """
        Tests Pydantic validation on SemanticSearchRequest.
        """
        req = SemanticSearchRequest(
            query="compliance and security audit",
            min_similarity=0.45,
            limit=15
        )
        self.assertEqual(req.query, "compliance and security audit")
        self.assertEqual(req.min_similarity, 0.45)
        self.assertEqual(req.limit, 15)
        self.assertTrue(req.include_context)

    def test_similar_chunks_request_validation(self):
        """
        Tests Pydantic validation on SimilarChunksRequest.
        """
        req = SimilarChunksRequest(
            text="Stage 1 STT and Stage 3 Mamba SSM run inside the tenant vault.",
            limit=5,
            min_similarity=0.5
        )
        self.assertEqual(req.limit, 5)
        self.assertEqual(req.min_similarity, 0.5)

    def test_query_embedding_search_flow(self):
        """
        Tests simulated in-memory vector ranking matching pgvector search semantics.
        """
        corpus = [
            "Good morning everyone. Let's begin the review on the Q3 enterprise memory rollout.",
            "Client compliance teams from Tier 1 law firms require full row-level isolation and zero data retention.",
            "Stage 1 WhisperX STT and Stage 3 Mamba SSM run entirely within the tenant vault.",
            "We have scheduled the 8GB VRAM swapping test with WhisperX and Mamba-3 2.8B for this Friday."
        ]

        query = "law firm data security and compliance"
        q_vec = self.service.embed_text(query, is_query=True)
        doc_vecs = self.service.embed_batch(corpus, is_query=False)

        scores = [self.service.compute_similarity(q_vec, d_vec) for d_vec in doc_vecs]
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        # The compliance/security chunk (index 1) or vault chunk (index 2) should rank at the top
        top_ranked_index = ranked_indices[0]
        self.assertIn(top_ranked_index, [1, 2])
        self.assertGreater(scores[top_ranked_index], scores[0])
