from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.codes import ErrorCode
from app.core.codes import SuccessCode
from app.core.exceptions import raise_business_exception
from app.core.deps import AdminUserIdDep, ComplaintPetitionServiceDep
from app.core.responses import success_response
from app.schemas.ComplaintEmailDTO import ComplaintPetitionBulkSendRequest
from app.services.internal.ComplaintPetitionSchedulerService import ComplaintPetitionSchedulerService

router = APIRouter(tags=["complaint-apply"])


@router.post("/complaint-admin/bootstrap")
async def bootstrap_complaint_departments(
    _admin_uid: AdminUserIdDep,
    complaint_petition_service: ComplaintPetitionServiceDep,
):
    try:
        result = await complaint_petition_service.bootstrap_from_vector()
        await complaint_petition_service.commit()
    except Exception:
        await complaint_petition_service.rollback()
        raise
    return success_response(
        result=result,
        success_code=SuccessCode.COMPLAINT_BOOTSTRAP_SUCCESS,
    )


@router.post("/complaint-email/apply/{issue_pin_id}")
async def apply_complaint_email(
    issue_pin_id: int,
    _admin_uid: AdminUserIdDep,
    complaint_petition_service: ComplaintPetitionServiceDep,
):
    try:
        result = await complaint_petition_service.create_petition_for_issue_pin(
            issue_pin_id=issue_pin_id,
            enforce_threshold=False,
        )
        await complaint_petition_service.commit()
    except Exception:
        await complaint_petition_service.rollback()
        raise
    return success_response(
        result=result.model_dump(),
        success_code=SuccessCode.COMPLAINT_APPLY_SUCCESS,
    )


@router.post("/complaint-email/send/bulk")
async def send_complaint_email_bulk(
    request: ComplaintPetitionBulkSendRequest,
    _admin_uid: AdminUserIdDep,
    complaint_petition_service: ComplaintPetitionServiceDep,
):
    try:
        result = await complaint_petition_service.send_bulk(request.petition_ids)
        await complaint_petition_service.commit()
    except Exception:
        await complaint_petition_service.rollback()
        raise
    return success_response(
        result=result.model_dump(),
        success_code=SuccessCode.COMPLAINT_BULK_SEND_SUCCESS,
    )


@router.post("/complaint-admin/scheduler/run-once")
async def run_complaint_scheduler_once(
    request: Request,
    _admin_uid: AdminUserIdDep,
):
    scheduler = getattr(request.app.state, "complaint_scheduler", None)
    if not isinstance(scheduler, ComplaintPetitionSchedulerService):
        raise_business_exception(
            ErrorCode.NOT_FOUND,
            "민원 자동 생성 스케줄러가 초기화되지 않았습니다.",
        )

    result = await scheduler.run_once_now()
    return success_response(
        result=result,
        success_code=SuccessCode.COMPLAINT_SCHEDULER_RUN_SUCCESS,
    )

