import io
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.deps import CurrentUserIdDep, S3UtilDep, UserServiceDep
from app.core.codes import ErrorCode, SuccessCode
from app.core.exceptions import raise_business_exception, raise_file_exception
from app.core.responses import success_response

router = APIRouter(prefix="/test", tags=["test"])

_DEFAULT_S3_TEST_PREFIX = "test-files"


@router.post("/s3/image-upload")
async def upload_test_image_to_s3(
    s3_util: S3UtilDep,
    file: UploadFile = File(...),
):
    uploaded = await s3_util.upload_file(file, prefix="test-images")
    return success_response(result=uploaded, success_code=SuccessCode.CREATED)


@router.post("/s3/upload")
async def upload_test_file_to_s3(
    s3_util: S3UtilDep,
    file: UploadFile = File(...),
    prefix: str = Query(default=_DEFAULT_S3_TEST_PREFIX, description="S3 object key prefix"),
):
    """이미지·PDF 등 임의 파일 업로드 테스트. 응답의 key로 다운로드 API를 호출할 수 있습니다."""
    raw = await file.read()
    if not raw:
        raise_file_exception(
            ErrorCode.FILE_UPLOAD_ERROR,
            detail="업로드할 파일이 비어 있습니다.",
        )

    filename = (file.filename or "upload.bin").strip() or "upload.bin"
    content_type = (file.content_type or "application/octet-stream").split(";")[0].strip()
    normalized_prefix = prefix.strip("/") or _DEFAULT_S3_TEST_PREFIX

    uploaded = await s3_util.upload_binary(
        raw,
        filename=filename,
        content_type=content_type,
        prefix=normalized_prefix,
    )
    return success_response(result=uploaded, success_code=SuccessCode.CREATED)


@router.get("/s3/download")
async def download_test_file_from_s3(
    s3_util: S3UtilDep,
    key: str = Query(..., min_length=1, description="S3 object key (업로드 응답의 key)"),
):
    """S3 object key로 파일 다운로드 테스트."""
    data, content_type = await s3_util.download_binary(key)
    filename = Path(key).name or "download.bin"
    return StreamingResponse(
        io.BytesIO(data),
        media_type=content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/s3/object")
async def delete_test_file_from_s3(
    s3_util: S3UtilDep,
    key: str = Query(..., min_length=1, description="삭제할 S3 object key"),
):
    """업로드 테스트 후 S3 객체 삭제."""
    deleted = await s3_util.delete_object(key)
    return success_response(
        result={"key": key, "deleted": deleted},
        success_code=SuccessCode.OK,
    )


@router.get("/user")
async def get_my_user(user_service: UserServiceDep, uid: CurrentUserIdDep):
    user = await user_service.get_user(uid)
    return success_response(result=user, success_code=SuccessCode.USER_INFO_GET_SUCCESS)


@router.get("/error")
async def raise_test_user_error():
    """에러 응답 포맷 테스트용 엔드포인트."""
    raise_business_exception(ErrorCode.USER_NOT_FOUND)
