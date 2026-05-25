from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from app.clients.PolicyNewsClient import PolicyNewsClient
from app.core.config import settings
from app.schemas.PolicyPinDTO import (
    PolicyPinHandoffDTO,
    PolicyPinHandoffResult,
    PolicyPinSearchResult,
    PolicyPinSourceDTO,
    PolicyPinTransformResult,
)
from app.services.policy_pin_transform import (
    POLICY_DOCUMENTS_PATH,
    POLICY_HANDOFF_PATH,
    transform_documents_jsonl,
)
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.fetch_policy_news import fetch_policy_documents

_MAX_HANDOFF_ITEMS = 500


class PolicyPinService:
    @staticmethod
    def documents_path() -> Path:
        return POLICY_DOCUMENTS_PATH

    @staticmethod
    def handoff_path() -> Path:
        return POLICY_HANDOFF_PATH

    async def search_and_save(
        self,
        *,
        start_date: str,
        end_date: str,
        limit: int | None = 10,
    ) -> PolicyPinSearchResult:
        fetch_limit: int | None
        if limit is None:
            fetch_limit = None
        else:
            fetch_limit = min(max(limit, 1), 50)

        async with PolicyNewsClient.from_settings() as client:
            documents, stats = await fetch_policy_documents(
                client=client,
                start_date=start_date,
                end_date=end_date,
                limit=fetch_limit,
            )

        path = self.documents_path()
        if documents:
            write_jsonl(path, documents)
        elif not path.is_file():
            write_jsonl(path, [])

        pins = [PolicyPinSourceDTO.model_validate(doc) for doc in documents]
        hint: str | None
        if len(pins) == 0:
            hint = (
                f"수집 0건 (API 호출 {stats.get('chunks', 0)}회). "
                "정책뉴스 API는 승인일 기준이며 미래 날짜 구간은 비어 있습니다. "
                "최근 3일로 다시 시도하세요 (예: start_date=20260522, end_date=20260524). "
                "기존 policy_documents.jsonl은 유지됩니다."
            )
        else:
            hint = (
                f"{len(pins)}건을 {path.name}에 저장했습니다. "
                "다음: POST /policy-pins/transform"
            )
        return PolicyPinSearchResult(
            query_start_date=start_date,
            query_end_date=end_date,
            count=len(pins),
            pins=pins,
            saved_documents_path=str(path),
            stats={k: int(v) for k, v in stats.items()},
            hint=hint,
        )

    async def transform_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
    ) -> PolicyPinTransformResult:
        result = await transform_documents_jsonl(limit=limit, model=model)
        if result.processed_count > 0:
            return result
        return result

    def load_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        limit: int | None = None,
    ) -> PolicyPinHandoffResult:
        path = file_path or self.handoff_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"핸드오프 JSONL 없음: {path}. POST /policy-pins/transform 를 먼저 실행하세요.",
            )

        effective_limit = _MAX_HANDOFF_ITEMS if limit is None else min(limit, _MAX_HANDOFF_ITEMS)

        pins: list[PolicyPinHandoffDTO] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                pins.append(PolicyPinHandoffDTO.from_row(json.loads(line)))

        total_in_file = len(pins)
        pins = pins[:effective_limit]

        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. GET /search → POST /transform 순서로 실행하세요."

        return PolicyPinHandoffResult(
            output_path=str(path),
            total_in_file=total_in_file,
            count=len(pins),
            pins=pins,
            hint=hint,
        )

    @staticmethod
    def default_date_range() -> tuple[str, str]:
        today = date.today()
        lookback = max(1, settings.policy_sync_lookback_days)
        start = today - timedelta(days=lookback - 1)
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
