from fastapi import APIRouter, File, UploadFile

from app.core.codes import SuccessCode
from app.core.deps import ImageExifLocationResolveServiceDep
from app.core.responses import success_response

router = APIRouter(prefix="/geo", tags=["geo"])


@router.post("/exif-point")
async def extract_exif_epsg4326_point(
    service: ImageExifLocationResolveServiceDep,
    file: UploadFile = File(..., description="EXIF GPS가 있을 수 있는 이미지"),
):
    """EXIF → WGS84 좌표 추출 후 `LOCATION_CORE_BASE_URL` 코어 `/api/location/resolve`로 주소·`location_id` 조회."""

    body = await service.extract_and_resolve(file)
    return success_response(result=body, success_code=SuccessCode.OK)
