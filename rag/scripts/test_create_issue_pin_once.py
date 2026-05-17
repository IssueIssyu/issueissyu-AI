"""로컬에서 IssueService.create_issue_pin 한 번 실행 (VLM → RAG → 핀 LLM).

  프로젝트 루트에서:

    python rag\\scripts\\test_create_issue_pin_once.py path\\to\\photo.jpg

  필요:
    - .env: GEMINI_API_KEY, DB URL 등 (VectorStoreService·DB)
    - 선택: LOCATION_CORE_BASE_URL (EXIF 역지오코딩, 기본 localhost:8080)
"""
from __future__ import annotations

import argparse
import asyncio
import io
import mimetypes
import sys
from pathlib import Path
from unittest.mock import MagicMock

import httpx
from starlette.datastructures import Headers, UploadFile

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def _run(
    image_path: Path,
    *,
    title: str,
    content: str,
    latitude: float,
    longitude: float,
) -> None:
    from app.core.config import settings
    from app.models.enum.ToneType import ToneType
    from app.repositories.IssuePinRepo import IssuePinRepo
    from app.repositories.PinRepo import PinRepo
    from app.repositories.UserRepo import UserRepo
    from app.schemas.IssueDTO import CreateIssuePinRequest
    from app.services.ImageExifLocationResolveService import ImageExifLocationResolveService
    from app.services.ImageMultipartGeoService import ImageMultipartGeoService
    from app.services.IssuePinLLMService import IssuePinLLMService
    from app.services.IssueService import IssueService
    from app.services.LocationResolveClient import LocationResolveClient
    from app.services.vector_domains import DomainVectorConfig, VectorDomain
    from app.services.VLMService import VLMService
    from app.services.VectorStoreService import VectorStoreService

    secret = settings.gemini_api_key
    if secret is None:
        print("GEMINI_API_KEY가 없습니다. .env 또는 환경 변수를 설정하세요.", file=sys.stderr)
        sys.exit(1)

    raw = image_path.read_bytes()
    mime, _ = mimetypes.guess_type(str(image_path))
    mime = mime or "image/jpeg"
    buf = io.BytesIO(raw)
    upload = UploadFile(
        file=buf,
        filename=image_path.name,
        headers=Headers({"content-type": mime}),
    )

    request = CreateIssuePinRequest(
        title=title,
        content=content,
        tone=ToneType.SITUATION_DESCRIPTION,
        latitude=latitude,
        longitude=longitude,
    )

    pin_repo = MagicMock(spec=PinRepo)
    issue_pin_repo = MagicMock(spec=IssuePinRepo)
    user_repo = MagicMock(spec=UserRepo)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.location_resolve_timeout_seconds),
    ) as http_client:
        location_resolve = LocationResolveClient(
            http_client=http_client,
            base_url=settings.location_core_base_url or "http://localhost:8080",
        )
        multipart_geo = ImageMultipartGeoService()
        exif_service = ImageExifLocationResolveService(multipart_geo, location_resolve)

        domain_configs = {
            VectorDomain.COMPLAINT: DomainVectorConfig(
                table_name="complaint",
                embedding_model=settings.gemini_embedding_model,
                embed_dim=settings.vector_embed_dim,
            ),
        }
        vector_store = VectorStoreService(
            database_url=settings.sync_database_url,
            async_database_url=settings.async_database_url,
            api_key=secret.get_secret_value(),
            table_name=settings.vector_table_name,
            default_embedding_model=settings.gemini_embedding_model,
            default_embed_dim=settings.vector_embed_dim,
            domain_configs=domain_configs,
            hybrid_search=settings.vector_hybrid_search,
            text_search_config=settings.vector_text_search_config,
            embedding_batch_size_override=settings.gemini_embedding_batch_size,
        )

        vlm = VLMService(
            api_key=secret.get_secret_value(),
            model_name=settings.gemini_vlm_model,
        )
        pin_llm = IssuePinLLMService(
            api_key=secret.get_secret_value(),
            model_name=settings.gemini_pin_text_model,
        )

        service = IssueService(
            vector_store_service=vector_store,
            vlm_service=vlm,
            image_exif_location_resolve_service=exif_service,
            issue_pin_llm_service=pin_llm,
            pin_repo=pin_repo,
            issue_pin_repo=issue_pin_repo,
            user_repo=user_repo,
        )

        result = await service.create_issue_pin(
            uid="script-test-user",
            images=[upload],
            request=request,
        )
        print(result.model_dump_json(indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="IssueService.create_issue_pin 로컬 테스트")
    parser.add_argument("image", type=Path, help="이미지 파일 경로")
    parser.add_argument("--title", default="테스트 민원", help="핀 제목")
    parser.add_argument("--content", default="현장 상황을 확인해 주세요.", help="핀 본문(민원 설명)")
    parser.add_argument("--lat", type=float, default=37.5665, help="위도")
    parser.add_argument("--lon", type=float, default=126.9780, help="경도")
    args = parser.parse_args()
    if not args.image.is_file():
        print(f"파일 없음: {args.image}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(
        _run(
            args.image,
            title=args.title,
            content=args.content,
            latitude=args.lat,
            longitude=args.lon,
        )
    )


if __name__ == "__main__":
    main()
