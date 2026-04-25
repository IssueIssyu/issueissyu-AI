from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import TypedDict
from urllib.parse import quote
from uuid import uuid4

from anyio import to_thread
import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile

from app.core.codes import ErrorCode
from app.core.config import settings
from app.core.exceptions import raise_file_exception

logger = logging.getLogger(__name__)


class UploadedImageResult(TypedDict):
    key: str
    url: str


class S3Util:
    ALLOWED_IMAGE_EXTENSIONS = {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".heic",
        ".heif",
    }

    def __init__(self, *, client: BaseClient | None = None) -> None:
        self.bucket_name = settings.aws_bucket_name
        self.region_name = settings.aws_region

        if client is not None:
            self.client = client
            return

        session_kwargs: dict[str, str] = {"region_name": self.region_name}
        if settings.aws_access_key and settings.aws_secret_key:
            session_kwargs["aws_access_key_id"] = settings.aws_access_key
            session_kwargs["aws_secret_access_key"] = settings.aws_secret_key

        self.client = boto3.client("s3", **session_kwargs)

    def _ensure_bucket_name(self) -> str:
        if not self.bucket_name:
            raise_file_exception(
                ErrorCode.FILE_UPLOAD_ERROR,
                detail="S3 bucket 설정이 없습니다. AWS_BUCKET 값을 확인해주세요.",
            )
        return self.bucket_name

    def _validate_image_file(self, upload_file: UploadFile) -> None:
        if not upload_file.filename:
            raise_file_exception(
                ErrorCode.FILE_UPLOAD_ERROR,
                detail="업로드할 파일명이 비어 있습니다.",
            )

        extension = Path(upload_file.filename).suffix.lower()
        if extension not in self.ALLOWED_IMAGE_EXTENSIONS:
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="이미지 파일만 업로드할 수 있습니다.",
            )

        content_type = (upload_file.content_type or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="이미지 MIME 타입만 업로드할 수 있습니다.",
            )

    @staticmethod
    def _build_object_key(filename: str, prefix: str = "uploads") -> str:
        normalized_prefix = prefix.strip("/")
        extension = Path(filename).suffix
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"{normalized_prefix}/{timestamp}-{uuid4().hex}{extension}"

    def _build_public_file_url(self, object_key: str) -> str:
        bucket_name = self._ensure_bucket_name()
        resolved_region = self.region_name or "us-east-1"
        encoded_key = quote(object_key.lstrip("/"), safe="/")
        if resolved_region == "us-east-1":
            return f"https://{bucket_name}.s3.amazonaws.com/{encoded_key}"
        return f"https://{bucket_name}.s3.{resolved_region}.amazonaws.com/{encoded_key}"

    async def upload_file(
        self,
        upload_file: UploadFile,
        *,
        object_key: str | None = None,
        prefix: str = "uploads",
        extra_args: dict[str, object] | None = None,
    ) -> UploadedImageResult:
        bucket_name = self._ensure_bucket_name()
        self._validate_image_file(upload_file)
        resolved_key = object_key or self._build_object_key(upload_file.filename, prefix)
        upload_args = dict(extra_args or {})
        if upload_file.content_type:
            upload_args.setdefault("ContentType", upload_file.content_type)

        await upload_file.seek(0)
        try:
            await to_thread.run_sync(
                lambda: self.client.upload_fileobj(
                    upload_file.file,
                    bucket_name,
                    resolved_key,
                    ExtraArgs=upload_args,
                )
                if upload_args
                else self.client.upload_fileobj(upload_file.file, bucket_name, resolved_key)
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("S3 파일 업로드 실패: %s", exc)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

        return {
            "key": resolved_key,
            "url": self._build_public_file_url(resolved_key),
        }

