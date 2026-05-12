from fastapi import APIRouter

from app.core.codes import SuccessCode
from app.core.responses import success_response
from app.models.enum.ToneType import ToneType

router = APIRouter(prefix="/issues", tags=["issue"])


@router.get("/tone-types")
async def get_tone_types():
    result = [{"key": t.name, "label": t.value} for t in ToneType]
    return success_response(result=result, success_code=SuccessCode.OK)
