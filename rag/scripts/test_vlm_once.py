"""로컬에서 VLM 한 번 호출 (API 없이). 프로젝트 루트에서 실행.

  python scripts\\test_vlm_once.py path\\to\\photo.jpg

  .env에 GEMINI_API_KEY 필요.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import mimetypes
import sys
from pathlib import Path

from starlette.datastructures import Headers, UploadFile

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


async def _run(
    image_path: Path,
    *,
    user_text: str,
    user_location: str | None,
    photo_address: str | None,
) -> None:
    from app.core.config import settings
    from app.services.VLMService import VLMService

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

    vlm = VLMService(
        api_key=secret.get_secret_value(),
        model_name=settings.gemini_vlm_model,
    )
    result = await vlm.analyze_image(
        user_text=user_text,
        images=[(upload, photo_address)],
        user_location=user_location,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="VLMService.analyze_image 로컬 테스트")
    parser.add_argument("image", type=Path, help="이미지 파일 경로")
    parser.add_argument("--user-text", default="민원 테스트", help="민원 텍스트")
    parser.add_argument("--user-location", default=None, help="사용자 위치")
    parser.add_argument("--photo-address", default=None, help="역지오코딩 주소")
    args = parser.parse_args()
    if not args.image.is_file():
        print(f"파일 없음: {args.image}", file=sys.stderr)
        sys.exit(1)
    asyncio.run(
        _run(
            args.image,
            user_text=args.user_text,
            user_location=args.user_location,
            photo_address=args.photo_address,
        )
    )


if __name__ == "__main__":
    main()
