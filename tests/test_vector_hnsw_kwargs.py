from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.core.config import Settings
from app.services.VectorStoreService import DEFAULT_HNSW_KWARGS, VectorStoreService
from app.services.vector_domains import build_hnsw_kwargs


class BuildHnswKwargsTest(unittest.TestCase):
    def test_build_hnsw_kwargs_from_settings(self) -> None:
        settings = Settings(
            VECTOR_HNSW_M=32,
            VECTOR_HNSW_EF_CONSTRUCTION=128,
            VECTOR_HNSW_EF_SEARCH=80,
            VECTOR_HNSW_DIST_METHOD="vector_cosine_ops",
        )

        self.assertEqual(
            build_hnsw_kwargs(settings),
            {
                "hnsw_m": 32,
                "hnsw_ef_construction": 128,
                "hnsw_ef_search": 80,
                "hnsw_dist_method": "vector_cosine_ops",
            },
        )

    def test_empty_dist_method_falls_back_to_default(self) -> None:
        settings = Settings(VECTOR_HNSW_DIST_METHOD="")

        self.assertEqual(settings.vector_hnsw_dist_method, "vector_cosine_ops")


class VectorStoreServiceHnswTest(unittest.TestCase):
    def test_get_or_create_bundle_passes_hnsw_kwargs(self) -> None:
        custom_kwargs = {
            "hnsw_m": 24,
            "hnsw_ef_construction": 96,
            "hnsw_ef_search": 60,
            "hnsw_dist_method": "vector_cosine_ops",
        }
        service = VectorStoreService(
            api_key="test-key",
            table_name="test_table",
            default_embedding_model="gemini-embedding-2",
            default_embed_dim=1536,
            hnsw_kwargs=custom_kwargs,
        )

        with (
            patch("app.services.VectorStoreService.PGVectorStore") as mock_pg,
            patch("app.services.VectorStoreService.VectorStoreIndex"),
            patch.object(service, "_get_or_create_embed_model", return_value=MagicMock()),
        ):
            service._get_or_create_bundle(
                resolved_table_name="complaint_chunks_complaint",
                embed_model_name="gemini-embedding-2",
                embed_dim=1536,
            )

        mock_pg.from_params.assert_called_once()
        self.assertEqual(mock_pg.from_params.call_args.kwargs["hnsw_kwargs"], custom_kwargs)

    def test_default_hnsw_kwargs_when_not_provided(self) -> None:
        service = VectorStoreService(
            api_key="test-key",
            table_name="test_table",
            default_embedding_model="gemini-embedding-2",
            default_embed_dim=1536,
        )

        self.assertEqual(service._hnsw_kwargs, DEFAULT_HNSW_KWARGS)


if __name__ == "__main__":
    unittest.main()
