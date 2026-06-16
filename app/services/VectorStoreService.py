from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from llama_index.core import VectorStoreIndex
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import BaseNode
from llama_index.core.vector_stores.types import MetadataFilters
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from starlette.concurrency import run_in_threadpool

from app.core.database import async_database_url as default_async_database_url
from app.core.database import sync_database_url as default_sync_database_url
from app.services.internal.ai.gemini_key_pool import GeminiKeyPool
from app.services.internal.ai.rotating_gemini_embedding import RotatingGoogleGenAIEmbedding
from app.services.vector_domains import DomainVectorConfig, VectorDomain

logger = logging.getLogger(__name__)

DEFAULT_HNSW_KWARGS: dict[str, Any] = {
    "hnsw_m": 16,
    "hnsw_ef_construction": 64,
    "hnsw_ef_search": 40,
    "hnsw_dist_method": "vector_cosine_ops",
}

@dataclass(slots=True)
class _VectorIndexBundle:
    table_name: str
    index: VectorStoreIndex


class VectorStoreService:
    def __init__(
        self,
        *,
        api_key: str,
        table_name: str,
        default_embedding_model: str,
        default_embed_dim: int,
        sync_database_url: str = default_sync_database_url,
        async_database_url: str = default_async_database_url,
        domain_configs: dict[VectorDomain, DomainVectorConfig] | None = None,
        hybrid_search: bool = True,
        text_search_config: str = "simple",
        embedding_batch_size_override: int | None = None,
        hnsw_kwargs: dict[str, Any] | None = None,
        key_pool: GeminiKeyPool | None = None,
    ) -> None:
        self._sync_database_url = sync_database_url
        self._async_database_url = async_database_url
        self._default_table_name = table_name
        self._default_embedding_model = default_embedding_model
        self._default_embed_dim = default_embed_dim
        self._hybrid_search = hybrid_search
        self._text_search_config = text_search_config
        self._api_key = api_key
        self._key_pool = key_pool
        self._bundles: dict[str, _VectorIndexBundle] = {}
        self._domain_configs = domain_configs or {}
        self._embed_models: dict[tuple[str, int], BaseEmbedding] = {}
        self._embedding_batch_size_override = embedding_batch_size_override
        self._hnsw_kwargs = hnsw_kwargs or dict(DEFAULT_HNSW_KWARGS)
        logger.info("Vector HNSW config: %s", self._hnsw_kwargs)

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        value = domain.strip().lower()
        value = re.sub(r"[^a-z0-9_]+", "_", value)
        value = re.sub(r"_+", "_", value).strip("_")
        if not value:
            raise ValueError("domain 값에는 영문자나 숫자가 최소 1개 이상 있어야 합니다.")
        return value

    def _resolve_table_name(self, *, domain: str | None, table_name: str | None) -> str:
        if table_name:
            return self._normalize_domain(table_name)
        if domain is None or not domain.strip():
            return self._default_table_name
        domain_config = self._resolve_domain_config(domain)
        if domain_config is not None:
            normalized = self._normalize_domain(domain_config.table_name)
            if domain_config.standalone_table:
                return normalized
        else:
            normalized = self._normalize_domain(domain)
        return f"{self._default_table_name}_{normalized}"

    def _resolve_domain_config(self, domain: str | None) -> DomainVectorConfig | None:
        if domain is None or not domain.strip():
            return None
        try:
            enum_domain = VectorDomain(domain.strip().lower())
        except ValueError:
            return None
        return self._domain_configs.get(enum_domain)

    def _get_or_create_embed_model(self, model_name: str, embed_dim: int) -> BaseEmbedding:
        model_key = (model_name, embed_dim)
        embed_model = self._embed_models.get(model_key)
        if embed_model is not None:
            return embed_model
        # gemini-embedding-2는 다중 입력 시 응답 수 불일치(KeyError) 이슈가 있어 기본 배치 1.
        # GEMINI_EMBEDDING_BATCH_SIZE로 올리면 처리량↑ (API/버전에 따라 실패할 수 있음).
        if self._embedding_batch_size_override is not None:
            embed_batch_size = max(1, int(self._embedding_batch_size_override))
        else:
            embed_batch_size = 1 if model_name.strip().endswith("embedding-2") else 10
        if self._key_pool is not None and self._key_pool.enabled:
            embed_model = RotatingGoogleGenAIEmbedding(
                key_pool=self._key_pool,
                model_name=model_name,
                embed_dim=embed_dim,
                embed_batch_size=embed_batch_size,
            )
        else:
            embed_model = GoogleGenAIEmbedding(
                model_name=model_name,
                api_key=self._api_key,
                embedding_config={"output_dimensionality": embed_dim},
                embed_batch_size=embed_batch_size,
            )
        self._embed_models[model_key] = embed_model
        return embed_model

    def _get_or_create_bundle(
        self,
        *,
        resolved_table_name: str,
        embed_model_name: str,
        embed_dim: int,
    ) -> _VectorIndexBundle:
        bundle = self._bundles.get(resolved_table_name)
        if bundle is not None:
            return bundle

        vector_store = PGVectorStore.from_params(
            connection_string=self._sync_database_url,
            async_connection_string=self._async_database_url,
            table_name=resolved_table_name,
            embed_dim=embed_dim,
            hybrid_search=self._hybrid_search,
            text_search_config=self._text_search_config,
            hnsw_kwargs=self._hnsw_kwargs,
        )
        bundle = _VectorIndexBundle(
            table_name=resolved_table_name,
            index=VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=self._get_or_create_embed_model(embed_model_name, embed_dim),
            ),
        )
        self._bundles[resolved_table_name] = bundle
        return bundle

    def _embedding_length(self, *, model_name: str, embed_dim: int) -> int:
        embed_model = self._get_or_create_embed_model(model_name, embed_dim)
        vector = embed_model.get_text_embedding("dimension validation probe")
        return len(vector)

    async def avalidate_embedding_dimensions(self) -> list[dict[str, Any]]:
        checks: list[tuple[str, str, int]] = [("default", self._default_embedding_model, self._default_embed_dim)]
        for domain, cfg in self._domain_configs.items():
            checks.append((domain.value, cfg.embedding_model, cfg.embed_dim))

        by_model_dim: dict[tuple[str, int], list[str]] = {}
        for scope, model_name, expected_dim in checks:
            key = (model_name, expected_dim)
            by_model_dim.setdefault(key, []).append(scope)

        results: list[dict[str, Any]] = []
        for (model_name, expected_dim), scopes in by_model_dim.items():
            actual_dim = await run_in_threadpool(
                self._embedding_length,
                model_name=model_name,
                embed_dim=expected_dim,
            )
            results.append(
                {
                    "model_name": model_name,
                    "expected_dim": expected_dim,
                    "actual_dim": actual_dim,
                    "matched": actual_dim == expected_dim,
                    "scopes": scopes,
                }
            )
        return results

    def get_table_name(self, *, domain: str | None = None, table_name: str | None = None) -> str:
        return self._resolve_table_name(domain=domain, table_name=table_name)

    async def ainsert_nodes(
        self,
        nodes: list[BaseNode],
        *,
        domain: VectorDomain | str | None = None,
        table_name: str | None = None,
    ) -> str:
        domain_value = domain.value if isinstance(domain, VectorDomain) else domain
        resolved_table_name = self._resolve_table_name(domain=domain_value, table_name=table_name)
        domain_config = self._resolve_domain_config(domain_value)
        embed_model_name = (
            domain_config.embedding_model if domain_config else self._default_embedding_model
        )
        embed_dim = domain_config.embed_dim if domain_config else self._default_embed_dim
        bundle = self._get_or_create_bundle(
            resolved_table_name=resolved_table_name,
            embed_model_name=embed_model_name,
            embed_dim=embed_dim,
        )
        await run_in_threadpool(bundle.index.insert_nodes, nodes)
        return resolved_table_name

    async def aretrieve(
        self,
        query: str,
        *,
        similarity_top_k: int = 5,
        filters: MetadataFilters | None = None,
        vector_store_query_mode: str = "hybrid",
        domain: VectorDomain | str | None = None,
        table_name: str | None = None,
    ):
        domain_value = domain.value if isinstance(domain, VectorDomain) else domain
        resolved_table_name = self._resolve_table_name(domain=domain_value, table_name=table_name)
        domain_config = self._resolve_domain_config(domain_value)
        embed_model_name = (
            domain_config.embedding_model if domain_config else self._default_embedding_model
        )
        embed_dim = domain_config.embed_dim if domain_config else self._default_embed_dim
        logger.warning(
            "aretrieve — table=%s, model=%s, dim=%d, mode=%s, top_k=%d, filters=%s",
            resolved_table_name, embed_model_name, embed_dim,
            vector_store_query_mode, similarity_top_k, filters,
        )
        bundle = self._get_or_create_bundle(
            resolved_table_name=resolved_table_name,
            embed_model_name=embed_model_name,
            embed_dim=embed_dim,
        )
        retriever = bundle.index.as_retriever(
            similarity_top_k=similarity_top_k,
            filters=filters,
            vector_store_query_mode=vector_store_query_mode,
        )
        results = await retriever.aretrieve(query)
        logger.warning("aretrieve — returned %d nodes", len(results))
        return results
