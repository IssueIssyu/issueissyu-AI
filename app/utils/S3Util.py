from __future__ import annotations

from datetime import UTC, datetime
import io
import logging
import mimetypes
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
            session_kwargs["aws_secret_access_key"] = settings.aws_secret_key.get_secret_value()

        self.client = boto3.client("s3", **session_kwargs)

    @staticmethod
    def resolve_image_mime(content_type: str | None, filename: str | None) -> str:
        mime = (content_type or "").split(";")[0].strip().lower()
        if not mime or mime == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(filename or "")
            mime = (guessed or "").split(";")[0].strip().lower()
        if mime == "image/jpg":
            mime = "image/jpeg"
        return mime

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

        content_type = self.resolve_image_mime(upload_file.content_type, upload_file.filename)
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
        cdn_base_url = (settings.cdn_base_url or "").strip()
        if settings.cdn_enabled and cdn_base_url:
            return f"{cdn_base_url.rstrip('/')}/{encoded_key}"
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

    async def upload_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        prefix: str = "uploads",
        object_key: str | None = None,
        extra_args: dict[str, object] | None = None,
    ) -> UploadedImageResult:
        if not data:
            raise_file_exception(
                ErrorCode.FILE_UPLOAD_ERROR,
                detail="업로드할 이미지 데이터가 비어 있습니다.",
            )
        extension = Path(filename).suffix.lower()
        if extension not in self.ALLOWED_IMAGE_EXTENSIONS:
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="이미지 파일만 업로드할 수 있습니다.",
            )
        if not content_type.lower().startswith("image/"):
            raise_file_exception(
                ErrorCode.FILE_TYPE_NOT_SUPPORTED,
                detail="이미지 MIME 타입만 업로드할 수 있습니다.",
            )

        bucket_name = self._ensure_bucket_name()
        resolved_key = object_key or self._build_object_key(filename, prefix)
        upload_args = dict(extra_args or {})
        upload_args.setdefault("ContentType", content_type)
        buffer = io.BytesIO(data)

        try:
            await to_thread.run_sync(
                lambda: self.client.upload_fileobj(
                    buffer,
                    bucket_name,
                    resolved_key,
                    ExtraArgs=upload_args,
                ),
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("S3 바이트 업로드 실패: %s", exc)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

        return {
            "key": resolved_key,
            "url": self._build_public_file_url(resolved_key),
        }

    async def upload_binary(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: str,
        prefix: str = "uploads",
        object_key: str | None = None,
        extra_args: dict[str, object] | None = None,
    ) -> UploadedImageResult:
        if not data:
            raise_file_exception(
                ErrorCode.FILE_UPLOAD_ERROR,
                detail="업로드할 데이터가 비어 있습니다.",
            )
        bucket_name = self._ensure_bucket_name()
        resolved_key = object_key or self._build_object_key(filename, prefix)
        upload_args = dict(extra_args or {})
        if content_type:
            upload_args.setdefault("ContentType", content_type)
        buffer = io.BytesIO(data)

        try:
            await to_thread.run_sync(
                lambda: self.client.upload_fileobj(
                    buffer,
                    bucket_name,
                    resolved_key,
                    ExtraArgs=upload_args,
                )
                if upload_args
                else self.client.upload_fileobj(buffer, bucket_name, resolved_key),
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("S3 바이너리 업로드 실패: %s", exc)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

        return {
            "key": resolved_key,
            "url": self._build_public_file_url(resolved_key),
        }

    async def download_bytes(self, object_key: str) -> tuple[bytes, str]:
        bucket_name = self._ensure_bucket_name()
        normalized_key = object_key.lstrip("/")

        def _download() -> tuple[bytes, str]:
            response = self.client.get_object(Bucket=bucket_name, Key=normalized_key)
            body = response["Body"].read()
            content_type = (response.get("ContentType") or "").split(";")[0].strip().lower()
            if not content_type or not content_type.startswith("image/"):
                guessed, _ = mimetypes.guess_type(normalized_key)
                content_type = (guessed or "image/jpeg").split(";")[0].strip().lower()
            return body, content_type

        try:
            return await to_thread.run_sync(_download)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("S3 바이트 다운로드 실패 key=%s err=%s", normalized_key, exc)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

    async def download_binary(self, object_key: str) -> tuple[bytes, str]:
        bucket_name = self._ensure_bucket_name()
        normalized_key = object_key.lstrip("/")

        def _download() -> tuple[bytes, str]:
            response = self.client.get_object(Bucket=bucket_name, Key=normalized_key)
            body = response["Body"].read()
            content_type = (response.get("ContentType") or "").split(";")[0].strip().lower()
            if not content_type:
                guessed, _ = mimetypes.guess_type(normalized_key)
                content_type = (guessed or "application/octet-stream").split(";")[0].strip().lower()
            return body, content_type

        try:
            return await to_thread.run_sync(_download)
        except (ClientError, BotoCoreError) as exc:
            logger.exception("S3 바이너리 다운로드 실패 key=%s err=%s", normalized_key, exc)
            raise_file_exception(ErrorCode.FILE_UPLOAD_ERROR)

    async def delete_object(self, object_key: str) -> bool:
        bucket_name = self._ensure_bucket_name()
        normalized_key = object_key.lstrip("/")

        def _delete() -> bool:
            try:
                self.client.delete_object(Bucket=bucket_name, Key=normalized_key)
                return True
            except ClientError as exc:
                error_code = (exc.response or {}).get("Error", {}).get("Code")
                # 이미 없는 객체는 삭제 성공으로 간주
                if error_code in {"NoSuchKey", "404"}:
                    logger.info("S3 삭제 대상 없음 key=%s", normalized_key)
                    return True
                logger.exception("S3 객체 삭제 실패 key=%s err=%s", normalized_key, exc)
                return False
            except BotoCoreError as exc:
                logger.exception("S3 객체 삭제 실패 key=%s err=%s", normalized_key, exc)
                return False

        return await to_thread.run_sync(_delete)

    async def delete_objects_best_effort(self, object_keys: list[str]) -> int:
        bucket_name = self._ensure_bucket_name()
        valid_keys = [k.lstrip("/") for k in object_keys if k.strip()]
        if not valid_keys:
            return 0

        chunk_size = 1000
        deleted_count = 0

        for i in range(0, len(valid_keys), chunk_size):
            chunk = valid_keys[i : i + chunk_size]

            def _delete_chunk() -> int:
                try:
                    response = self.client.delete_objects(
                        Bucket=bucket_name,
                        Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": False},
                    )
                    deleted_items = response.get("Deleted", []) or []
                    errors = response.get("Errors", []) or []

                    tolerated_missing = sum(
                        1
                        for err in errors
                        if err.get("Code") in {"NoSuchKey", "404"}
                    )
                    unexpected_errors = [
                        err for err in errors if err.get("Code") not in {"NoSuchKey", "404"}
                    ]
                    for err in unexpected_errors:
                        logger.warning(
                            "S3 배치 삭제 일부 실패 key=%s code=%s message=%s",
                            err.get("Key"),
                            err.get("Code"),
                            err.get("Message"),
                        )
                    return len(deleted_items) + tolerated_missing
                except (ClientError, BotoCoreError) as exc:
                    logger.exception(
                        "S3 batch delete failed chunk_size=%s err=%s",
                        len(chunk),
                        exc,
                    )
                    return 0

            deleted_count += await to_thread.run_sync(_delete_chunk)

        return deleted_count

