from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from pydantic import ValidationError

from app.core.codes import ErrorCode, SuccessCode
from app.core.deps import CurrentUserIdDep, IssueServiceDep
from app.core.exceptions import raise_business_exception
from app.core.responses import success_response
from app.models.enum.ToneType import ToneType
from app.schemas.IssueDTO import (
    CreateIssuePinMultipartRequest,
    CreateIssuePinRequest,
    UpdateIssuePinMultipartRequest,
)

router = APIRouter(prefix="/issues", tags=["issue"])


@router.get("/tone-types")
async def get_tone_types():
    result = [{"key": t.name, "label": t.value} for t in ToneType]
    return success_response(result=result, success_code=SuccessCode.OK)


@router.post("/pin/ai")
async def create_issue_pin_ai(
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
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
        request=request,
    )
    return success_response(result=result, success_code=SuccessCode.CREATED)


@router.post("/pin")
async def create_issue_pin(
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
    background_tasks: BackgroundTasks,
    request: Annotated[str, Form(...)],
    photos: list[UploadFile] = File(default=[]),
):
    try:
        body = CreateIssuePinMultipartRequest.model_validate_json(request)
    except ValidationError:
        raise_business_exception(ErrorCode.ISSUE_PIN_IMPORT_VALIDATION)

    result = await issue_service.create_issue_pin(
        uid=uid,
        request=body,
        photos=photos,
        background_tasks=background_tasks,
    )
    return success_response(
        result=result.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.ISSUE_PIN_IMPORT_SUCCESS,
    )


@router.get("/pin/{pin_id}/reliability")
async def get_issue_pin_reliability(
    pin_id: int,
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
):
    result = await issue_service.get_issue_pin_reliability(
        uid=uid,
        pin_id=pin_id,
    )
    return success_response(
        result=result.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.ISSUE_PIN_RELIABILITY_GET_SUCCESS,
    )


@router.patch("/pin/{pin_id}")
async def update_issue_pin(
    pin_id: int,
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
    background_tasks: BackgroundTasks,
    request: Annotated[str, Form(...)],
    photos: list[UploadFile] = File(default=[]),
):
    try:
        body = UpdateIssuePinMultipartRequest.model_validate_json(request)
    except ValidationError:
        raise_business_exception(ErrorCode.ISSUE_PIN_EDIT_VALIDATION)

    result = await issue_service.update_issue_pin(
        uid=uid,
        pin_id=pin_id,
        request=body,
        photos=photos,
        background_tasks=background_tasks,
    )
    return success_response(
        result=result.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.ISSUE_PIN_EDIT_SUCCESS,
    )


@router.get("/pin/{issue_pin_id}")
async def get_issue_pin_detail(
    issue_pin_id: int,
    uid: CurrentUserIdDep,
    issue_service: IssueServiceDep,
):
    result = await issue_service.get_issue_pin_detail(
        uid=uid,
        issue_pin_id=issue_pin_id,
    )
    return success_response(
        result=result.model_dump(by_alias=True, exclude_none=False),
        success_code=SuccessCode.ISSUE_PIN_GET_SUCCESS,
    )
