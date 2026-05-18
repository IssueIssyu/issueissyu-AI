from __future__ import annotations

import logging
from typing import Any

from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.PinRepo import PinRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.IssueDTO import CreateIssuePinRequest, IssueAnalysisResult
from app.services.VectorStoreService import VectorStoreService
from app.services.internal.ai.IssuePinLLMService import IssuePinLLMService
from app.services.internal.ai.IssueRagPlannerService import IssueRagPlannerService
from app.services.internal.geo.LocationResolveClient import LocationResolveClient
from app.services.prompts import build_issue_pin_prompt_from_pipeline_bundle
from app.services.vector_domains import VectorDomain

logger = logging.getLogger(__name__)
SINGLE_RETRIEVAL_TOP_K = 5


class IssueService:
    def __init__(
        self,
        vector_store_service: VectorStoreService,
        issue_rag_planner_service: IssueRagPlannerService,
        location_resolve_client: LocationResolveClient,
        issue_pin_llm_service: IssuePinLLMService,
        pin_repo: PinRepo,
        issue_pin_repo: IssuePinRepo,
        user_repo: UserRepo,
    ) -> None:
        self._vector_store_service = vector_store_service
        self._issue_rag_planner_service = issue_rag_planner_service
        self._location_resolve_client = location_resolve_client
        self._issue_pin_llm_service = issue_pin_llm_service
        self._pin_repo = pin_repo
        self._issue_pin_repo = issue_pin_repo
        self._user_repo = user_repo

    @staticmethod
    def _user_coordinates_from_request(request: CreateIssuePinRequest) -> str:
        return f"{request.latitude:.6f},{request.longitude:.6f}"

    async def _resolve_user_location_address(self, request: CreateIssuePinRequest) -> str | None:
        resolved = await self._location_resolve_client.resolve_wgs84(
            latitude=request.latitude,
            longitude=request.longitude,
        )
        if resolved is None:
            return None
        address = (resolved.address or "").strip()
        return address or None

    @staticmethod
    def _rag_hits_to_dicts(hits: list[Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for hit in hits:
            node = hit.node
            meta = node.metadata if node.metadata is not None else {}
            rows.append(
                {
                    "text": node.get_content(),
                    "score": hit.score,
                    "metadata": dict(meta) if hasattr(meta, "items") else {},
                }
            )
        return rows

    @staticmethod
    def _sanitize_single_query(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 180:
            text = text[:180].rstrip()
        return text

    @staticmethod
    def _tune_title(*, original_title: str, rewritten: dict[str, Any]) -> str:
        primary = rewritten.get("primary_query")
        keyword = rewritten.get("keyword_query")
        candidate = (
            IssueService._sanitize_single_query(primary)
            or IssueService._sanitize_single_query(keyword)
            or original_title.strip()
        )
        # 제목은 짧고 선명하게: 불필요한 접미 구두점 제거 + 길이 제한
        tuned = candidate.strip().rstrip(" .,!?:;")
        if len(tuned) > 42:
            tuned = tuned[:42].rstrip()
        return tuned or "민원 제보"

    async def issue_pin_ai_make(
        self,
        *,
        uid: str,
        request: CreateIssuePinRequest,
    ) -> IssueAnalysisResult:
        _ = uid
        safe_title = request.title.strip()
        safe_content = request.content.strip()
        user_content = f"title:{safe_title}\ncontent:{safe_content}\n".strip()
        user_location = await self._resolve_user_location_address(request)
        if user_location is None:
            user_location = "주소 확인 불가"
        user_coordinates = self._user_coordinates_from_request(request)

        rewritten = await self._issue_rag_planner_service.rewrite_queries(
            title=safe_title,
            content=safe_content,
            user_location=user_coordinates,
        )
        filters = None
        primary_query = self._sanitize_single_query(rewritten.get("primary_query"))
        keyword_query = self._sanitize_single_query(rewritten.get("keyword_query"))
        selected_query = primary_query or keyword_query or user_content
        logger.warning(
            "Issue RAG retrieve start — single_query=%r source=%s domain=%s filters=%s top_k=%d",
            selected_query,
            "primary" if primary_query else ("keyword" if keyword_query else "fallback"),
            VectorDomain.COMPLAINT.value,
            filters,
            SINGLE_RETRIEVAL_TOP_K,
        )

        rag_hits = await self._vector_store_service.aretrieve(
            query=selected_query,
            domain=VectorDomain.COMPLAINT,
            similarity_top_k=SINGLE_RETRIEVAL_TOP_K,
            filters=filters,
        )
        if len(rag_hits) > SINGLE_RETRIEVAL_TOP_K:
            logger.warning(
                "Issue RAG capped hits: raw=%d capped=%d",
                len(rag_hits),
                SINGLE_RETRIEVAL_TOP_K,
            )
            rag_hits = rag_hits[:SINGLE_RETRIEVAL_TOP_K]
        rag_payload = self._rag_hits_to_dicts(rag_hits)
        logger.warning("Issue RAG hits=%d", len(rag_hits))

        bundle: dict[str, Any] = {
            "issue": {
                "title": safe_title,
                "content": safe_content,
                "tone": request.tone,
                "location": user_location,
            },
            "rag_queries": [selected_query],
            "rag_filters_applied": filters is not None,
            "rag_hits": rag_payload,
        }
        pin_prompt = build_issue_pin_prompt_from_pipeline_bundle(bundle)
        pin_body = await self._issue_pin_llm_service.generate_pin_text(prompt=pin_prompt)
        tuned_title = self._tune_title(
            original_title=request.title,
            rewritten=rewritten,
        )

        return IssueAnalysisResult(
            title=tuned_title,
            content=pin_body,
        )
