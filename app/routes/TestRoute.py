from fastapi import APIRouter, File, UploadFile


from app.core.deps import S3UtilDep, UserServiceDep
from app.core.codes import ErrorCode, SuccessCode
from app.core.exceptions import raise_business_exception
from app.core.responses import success_response
router = APIRouter(prefix="/test", tags=["test"])


@router.post("/s3/image-upload")
async def upload_test_image_to_s3(
    s3_util: S3UtilDep,
    file: UploadFile = File(...),
):
    uploaded = await s3_util.upload_file(file, prefix="test-images")
    return success_response(result=uploaded, success_code=SuccessCode.CREATED)


@router.get("/user")
async def get_all_users(user_service: UserServiceDep):
    users = await user_service.get_all_users()
    return success_response(result=users, success_code=SuccessCode.USER_INFO_GET_SUCCESS)


@router.post("/user")
async def create_test_user(
    user_service: UserServiceDep,
    email: str = "test@issueissyu.ai",
    nickname: str = "tester",
    phone: str | None = None,
):
    user = await user_service.create_test_user(
        email=email,
        nickname=nickname,
        phone=phone,
    )
    return success_response(result=user, success_code=SuccessCode.CREATED)

@router.get("/test/error")
async def raise_test_user_error():
    """에러 응답 포맷 테스트용 엔드포인트."""
    raise_business_exception(ErrorCode.USER_NOT_FOUND)
