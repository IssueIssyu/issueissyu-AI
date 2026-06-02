from __future__ import annotations

import json
from functools import partial
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.clients.VisitKoreaClient import VisitKoreaClient
from app.schemas.FestivalPinDTO import (
    FestivalPinDTO,
    FestivalPinHandoffResult,
    FestivalPinSearchResult,
    FestivalPinSourceDTO,
    FestivalPinTransformResult,
)
from app.services.festival_pin_transform import (
    FESTIVAL_DOCUMENTS_PATH,
    FESTIVAL_HANDOFF_PATH,
    build_handoff_row,
    transform_documents_jsonl,
)
from app.utils.festival_date_filter import festival_overlaps_range
from rag.scripts.chunk_module import write_jsonl
from rag.scripts.fetch_visitkorea import fetch_festival_documents

_MAX_HANDOFF_ITEMS = 500

__all__ = ["FestivalPinService", "build_handoff_row"]


class FestivalPinService:
    @staticmethod
    def documents_path() -> Path:
        return FESTIVAL_DOCUMENTS_PATH

    @staticmethod
    def handoff_path() -> Path:
        return FESTIVAL_HANDOFF_PATH

    async def search_and_save(
        self,
        *,
        start_date: str,
        end_date: str,
        limit: int | None = 10,
        uncapped: bool = False,
    ) -> FestivalPinSearchResult:
        fetch_limit: int | None
        if limit is None:
            fetch_limit = None
        elif uncapped:
            fetch_limit = max(limit, 1)
        else:
            fetch_limit = min(max(limit, 1), 50)

        async with VisitKoreaClient.from_settings() as client:
            documents, stats = await fetch_festival_documents(
                client=client,
                start_date=start_date,
                end_date=end_date,
                num_of_rows=100,
                max_pages=None,
                limit=fetch_limit,
                skip_detail=False,
                fetch_images=True,
                save_raw_pages=False,
            )

        path = self.documents_path()
        write_jsonl(path, documents)

        pins = [FestivalPinSourceDTO.model_validate(doc) for doc in documents]
        return FestivalPinSearchResult(
            query_start_date=start_date,
            query_end_date=end_date,
            count=len(pins),
            pins=pins,
            saved_documents_path=str(path),
            stats={k: int(v) for k, v in stats.items()},
            hint=(
                f"{len(pins)}건을 {path.name}에 저장했습니다. "
                "다음: POST /festival-pins/transform"
            ),
        )

    async def transform_and_save(
        self,
        *,
        limit: int | None = None,
        model: str | None = None,
    ) -> FestivalPinTransformResult:
        result = await transform_documents_jsonl(limit=limit, model=model)
        if result.processed_count > 0:
            return result.model_copy(
                update={
                    "hint": (
                        f"{result.processed_count}건을 festival_pins_for_db.jsonl에 저장했습니다. "
                        "다음: GET /festival-pins/handoff"
                    ),
                },
            )
        return result

    def load_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> FestivalPinHandoffResult:
        path = file_path or self.handoff_path()
        if not path.is_file():
            raise FileNotFoundError(
                f"핸드오프 JSONL 없음: {path}. POST /festival-pins/transform 를 먼저 실행하세요.",
            )

        effective_limit = _MAX_HANDOFF_ITEMS if limit is None else min(limit, _MAX_HANDOFF_ITEMS)
        use_date_filter = start_date is not None and end_date is not None

        matched: list[FestivalPinDTO] = []
        total_in_file = 0

        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_in_file += 1
                row = json.loads(line)
                item = FestivalPinDTO.model_validate(row)

                if use_date_filter and not festival_overlaps_range(
                    event_start=item.event_start_time,
                    event_end=item.event_end_time,
                    query_start=start_date,
                    query_end=end_date,
                ):
                    continue

                matched.append(item)

        pins = matched[:effective_limit]

        hint: str | None = None
        if total_in_file == 0:
            hint = "JSONL이 비어 있습니다. GET /search → POST /transform 순서로 실행하세요."
        elif len(pins) == 0:
            if use_date_filter:
                hint = (
                    "기간 필터에 맞는 축제가 없습니다. start_date/end_date를 비우거나 "
                    "search 기간을 넓혀 다시 수집하세요."
                )
            else:
                hint = "조회 결과가 없습니다."
        elif len(pins) == 1 and total_in_file > 1 and use_date_filter:
            hint = (
                f"파일 {total_in_file}건 중 기간 필터 후 1건입니다. "
                "날짜를 넓히거나 파라미터를 비우세요."
            )

        return FestivalPinHandoffResult(
            filter_start_date=start_date,
            filter_end_date=end_date,
            total_in_file=total_in_file,
            matched_count=len(matched),
            count=len(pins),
            pins=pins,
            hint=hint,
        )

    async def aload_from_jsonl(
        self,
        *,
        file_path: Path | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> FestivalPinHandoffResult:
        return await run_in_threadpool(
            partial(
                self.load_from_jsonl,
                file_path=file_path,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
            ),
        )
