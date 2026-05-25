from __future__ import annotations

from fastapi import APIRouter

from app.core.codes import SuccessCode
from app.core.deps import AdminUserIdDep, ComplaintPetitionServiceDep, CurrentUserIdDep
from app.core.responses import success_response
from app.schemas.ComplaintEmailDTO import ComplaintPetitionBulkSendRequest

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
    _uid: CurrentUserIdDep,
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


@router.post("/complaint-email/generate/force/{issue_pin_id}")
async def force_generate_complaint_email(
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
        success_code=SuccessCode.COMPLAINT_FORCE_GENERATE_SUCCESS,
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

