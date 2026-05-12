from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.core.codes import SuccessCode
from app.core.deps import CurrentUserIdDep, IssueServiceDep
from app.core.responses import success_response
from app.models.enum.ToneType import ToneType
from app.schemas.IssueDTO import CreateIssuePinRequest

router = APIRouter(prefix="/issues", tags=["issue"])


@router.get("/tone-types")
async def get_tone_types():
    result = [{"key": t.name, "label": t.value} for t in ToneType]
    return success_response(result=result, success_code=SuccessCode.OK)


@router.post("/pin/ai")
async def create_issue_pin_ai(
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
    images: Annotated[list[UploadFile], File(...)],
    title: str = Form(...),
    content: str = Form(...),
    tone: ToneType = Form(ToneType.NONE),
    latitude: float = Form(...),
    longitude: float = Form(...),
):
    request = CreateIssuePinRequest(
        title=title,
        content=content,
        tone=tone,
        latitude=latitude,
        longitude=longitude,
    )
    result = await issue_service.issue_pin_ai_make(
        uid=uid,
        images=images,
        request=request,
    )
    return success_response(result=result, success_code=SuccessCode.CREATED)
