from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
import io
import logging
import re
from typing import Sequence
from zoneinfo import ZoneInfo

from fastapi import UploadFile
from starlette.datastructures import Headers

from app.core.codes import ErrorCode
from app.core.exceptions import raise_business_exception
from app.models.ComplaintPetition import ComplaintPetition
from app.models.Department import Department
from app.models.LocationDepartment import LocationDepartment
from app.models.enum.ComplaintPetitionStatus import ComplaintPetitionStatus
from app.models.enum.IssuePinState import IssuePinState
from app.models.enum.UserRole import UserRole
from app.repositories.ComplaintPetitionRepo import ComplaintPetitionRepo
from app.repositories.DepartmentRepo import DepartmentRepo
from app.repositories.IssuePinRepo import IssuePinRepo
from app.repositories.LocationDepartmentRepo import LocationDepartmentRepo
from app.repositories.LocationRepo import LocationRepo
from app.repositories.UserRepo import UserRepo
from app.schemas.ComplaintEmailDTO import (
    ComplaintPetitionApplyResponse,
    ComplaintPetitionBulkSendItem,
    ComplaintPetitionBulkSendResponse,
)
from app.schemas.IssueDTO import ImageWithLocation
from app.services.ComplaintEmailService import ComplaintEmailService
from app.services.department_catalog import CURATED_CATEGORY_NAMES
from app.utils.S3Util import S3Util

logger = logging.getLogger(__name__)

_KST = ZoneInfo("Asia/Seoul")
_S3_PDF_PREFIX = "complaint-petition"
_DEFAULT_SEED_EMAIL_DOMAIN = "placeholder.local"
_SAFE_DEPT_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")


@dataclass(slots=True)
class ComplaintPetitionService:
    complaint_email_service: ComplaintEmailService
    issue_pin_repo: IssuePinRepo
    location_department_repo: LocationDepartmentRepo
    complaint_petition_repo: ComplaintPetitionRepo
    department_repo: DepartmentRepo
    location_repo: LocationRepo
    user_repo: UserRepo
    s3_util: S3Util

    async def commit(self) -> None:
        await self.complaint_petition_repo.commit()

    async def rollback(self) -> None:
        await self.complaint_petition_repo.rollback()

    async def assert_admin(self, *, uid: str) -> None:
        user = await self.user_repo.get_by_uid(uid)
        if user is None:
            raise_business_exception(ErrorCode.USER_NOT_FOUND)
        if user.role != UserRole.ADMIN:
            raise_business_exception(ErrorCode.FORBIDDEN, "ADMIN 권한이 필요합니다.")

    async def bootstrap_from_vector(self) -> dict[str, int]:
        categories = list(CURATED_CATEGORY_NAMES)
        if not categories:
            raise_business_exception(
                ErrorCode.NOT_FOUND,
                "고정 카테고리 목록이 비어 있습니다.",
            )

        existing = await self.department_repo.get_by_names(categories)
        existing_map = {row.department_name: row for row in existing}

        created_dept = 0
        for department_name in categories:
            if department_name in existing_map:
                continue
            await self.department_repo.save(
                Department(department_name=department_name),
                flush_immediately=True,
            )
            created_dept += 1
        await self.department_repo.flush()
        all_departments = await self.department_repo.get_all_ordered()
        locations = await self.location_repo.get_all_ordered()

        created_pairs = 0
        for location in locations:
            for department in all_departments:
                existing_pair = await self.location_department_repo.get_by_location_and_department_id(
                    location_id=location.location_id,
                    department_id=department.department_id,
                )
                if existing_pair is not None:
                    continue
                await self.location_department_repo.save(
                    LocationDepartment(
                        location_id=location.location_id,
                        department_id=department.department_id,
                        location_department_email=self._default_seed_email(
                            location_id=location.location_id,
                            department_name=department.department_name,
                        ),
                        is_active=True,
                    ),
                    flush_immediately=True,
                )
                created_pairs += 1

        return {
            "departments": len(all_departments),
            "locations": len(locations),
            "created_departments": created_dept,
            "created_location_departments": created_pairs,
        }

    async def create_petition_for_issue_pin(
        self,
        *,
        issue_pin_id: int,
        generated_on: date | None = None,
        enforce_threshold: bool = True,
    ) -> ComplaintPetitionApplyResponse:
        issue_pin = await self.issue_pin_repo.get_by_issue_pin_id(issue_pin_id)
        if issue_pin is None or issue_pin.pin is None:
            raise_business_exception(ErrorCode.ISSUE_NOT_FOUND)

        if enforce_threshold and issue_pin.petition_count < 30:
            raise_business_exception(
                ErrorCode.VALIDATION_ERROR,
                "petition_count가 30 미만이라 자동 생성 대상이 아닙니다.",
            )

        pin = issue_pin.pin
        pin_location = pin.pin_location
        if pin_location is None:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "핀 위치 정보가 없습니다.")
        location_id = pin_location.location_id

        target_generated_on = generated_on or self._today_kst()
        exists = await self.complaint_petition_repo.exists_by_issue_pin_and_generated_on(
            issue_pin_id=issue_pin_id,
            generated_on=target_generated_on,
        )
        if exists:
            raise_business_exception(
                ErrorCode.VALIDATION_ERROR,
                "해당 이슈핀은 오늘 이미 생성되었습니다.",
            )

        images = await self._load_pin_images(pin.pin_images, fallback_address=pin_location.detail_address)
        generated = await self.complaint_email_service.generate_petition_package(
            pin_title=pin.pin_title,
            pin_content=pin.pin_content,
            images=images,
            photo_address=pin_location.detail_address,
        )
        department_name = (generated.department or "").strip()
        if not department_name:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "추천 카테고리를 찾지 못했습니다.")

        location_department = await self.location_department_repo.get_by_location_and_department_name(
            location_id=location_id,
            department_name=department_name,
        )
        if location_department is None:
            raise_business_exception(
                ErrorCode.NOT_FOUND,
                "해당 위치와 부서 조합의 매핑이 없습니다.",
            )
        if not location_department.is_active:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "비활성화된 부서 매핑입니다.")

        pdf_upload = await self.s3_util.upload_binary(
            generated.opinion_pdf_bytes,
            filename=f"petition-{issue_pin_id}-{target_generated_on.isoformat()}.pdf",
            content_type="application/pdf",
            prefix=_S3_PDF_PREFIX,
        )

        subject = generated.notification_email_subject.strip() or f"[민원 자동 생성] {pin.pin_title}"
        body = generated.notification_email_body.strip()
        if not body:
            raise_business_exception(ErrorCode.INTERNAL_SERVER_ERROR, "메일 본문 생성에 실패했습니다.")
        reliability_basis = generated.reliability_basis.strip() or "검증 근거 없음"

        petition = ComplaintPetition(
            location_department_id=location_department.location_department_id,
            issue_pin_id=issue_pin.issue_pin_id,
            generated_on=target_generated_on,
            pdf_s3_key=pdf_upload["key"],
            pdf_s3_url=pdf_upload["url"],
            email_subject=subject,
            email_body=body,
            reliability_score=generated.reliability_score,
            reliability_basis=reliability_basis,
            status=ComplaintPetitionStatus.CREATED.value,
        )
        await self.complaint_petition_repo.save(petition, flush_immediately=True)

        return ComplaintPetitionApplyResponse(
            petition_id=petition.petition_id,
            issue_pin_id=issue_pin.issue_pin_id,
            location_department_id=location_department.location_department_id,
            location_id=location_id,
            department_name=location_department.department.department_name,
            location_department_email=location_department.location_department_email,
            generated_on=target_generated_on.isoformat(),
            pdf_s3_key=petition.pdf_s3_key,
            pdf_s3_url=petition.pdf_s3_url,
            email_subject=petition.email_subject,
            email_body=petition.email_body,
            reliability_score=petition.reliability_score,
            reliability_basis=petition.reliability_basis,
            status=petition.status,
        )

    async def create_scheduled_petitions(self, *, threshold: int = 30) -> dict[str, int]:
        generated_on = self._today_kst()
        offset = 0
        batch_size = 100
        success_count = 0
        skip_count = 0
        fail_count = 0

        while True:
            rows = await self.issue_pin_repo.list_by_petition_count_gte(
                threshold=threshold,
                limit=batch_size,
                offset=offset,
            )
            if not rows:
                break
            offset += len(rows)
            for issue_pin in rows:
                try:
                    await self.create_petition_for_issue_pin(
                        issue_pin_id=issue_pin.issue_pin_id,
                        generated_on=generated_on,
                        enforce_threshold=False,
                    )
                    success_count += 1
                except Exception as exc:
                    message = str(exc)
                    if "오늘 이미 생성" in message:
                        skip_count += 1
                        continue
                    fail_count += 1
                    logger.exception(
                        "스케줄 민원 생성 실패 issue_pin_id=%s error=%s",
                        issue_pin.issue_pin_id,
                        exc,
                    )

        return {
            "generated_on": int(generated_on.strftime("%Y%m%d")),
            "success_count": success_count,
            "skip_count": skip_count,
            "fail_count": fail_count,
        }

    async def send_bulk(self, petition_ids: list[int]) -> ComplaintPetitionBulkSendResponse:
        rows = await self.complaint_petition_repo.get_by_petition_ids(petition_ids)
        by_id = {row.petition_id: row for row in rows}
        sent_count = 0
        failed_count = 0
        items: list[ComplaintPetitionBulkSendItem] = []

        for petition_id in petition_ids:
            petition = by_id.get(petition_id)
            if petition is None:
                failed_count += 1
                items.append(
                    ComplaintPetitionBulkSendItem(
                        petition_id=petition_id,
                        status=ComplaintPetitionStatus.FAILED.value,
                        issue_pin_id=0,
                        location_department_id=0,
                        location_department_email="",
                        reason="민원 신청 이력을 찾지 못했습니다.",
                    ),
                )
                continue
            if petition.status != ComplaintPetitionStatus.CREATED.value:
                failed_count += 1
                items.append(
                    ComplaintPetitionBulkSendItem(
                        petition_id=petition.petition_id,
                        status=petition.status,
                        issue_pin_id=petition.issue_pin_id,
                        location_department_id=petition.location_department_id,
                        location_department_email=petition.location_department.location_department_email,
                        reason="CREATED 상태만 송신할 수 있습니다.",
                    ),
                )
                continue
            send_ok, reason = self._send_one(petition)
            next_status = ComplaintPetitionStatus.SENT if send_ok else ComplaintPetitionStatus.FAILED
            await self.complaint_petition_repo.update_status(
                petition_id=petition.petition_id,
                status=next_status.value,
            )
            if send_ok:
                sent_count += 1
                await self.issue_pin_repo.update_state(
                    petition.issue_pin_id,
                    IssuePinState.IN_PROGRESS,
                )
            else:
                failed_count += 1

            items.append(
                ComplaintPetitionBulkSendItem(
                    petition_id=petition.petition_id,
                    status=next_status.value,
                    issue_pin_id=petition.issue_pin_id,
                    location_department_id=petition.location_department_id,
                    location_department_email=petition.location_department.location_department_email,
                    reason=reason,
                ),
            )

        return ComplaintPetitionBulkSendResponse(
            sent_count=sent_count,
            failed_count=failed_count,
            items=items,
        )

    @staticmethod
    def _send_one(petition: ComplaintPetition) -> tuple[bool, str | None]:
        email = petition.location_department.location_department_email.strip()
        if not email:
            return False, "부서 이메일이 비어 있습니다."
        # 실제 메일 전송 연동 지점.
        return True, None

    async def _load_pin_images(
        self,
        pin_images: Sequence,
        *,
        fallback_address: str | None,
    ) -> list[ImageWithLocation]:
        rows: list[ImageWithLocation] = []
        sorted_images = sorted(
            pin_images,
            key=lambda item: (not item.is_main, item.pin_image_id),
        )
        for pin_image in sorted_images:
            data, content_type = await self.s3_util.download_bytes(pin_image.pin_s3_key)
            upload = UploadFile(
                file=io.BytesIO(data),
                filename=pin_image.pin_s3_key.rsplit("/", maxsplit=1)[-1] or "image.jpg",
                headers=Headers({"content-type": content_type}),
            )
            rows.append(
                ImageWithLocation(
                    image=upload,
                    address=fallback_address,
                ),
            )
        if not rows:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "민원 생성을 위한 이미지가 없습니다.")
        return rows

    @staticmethod
    def _default_seed_email(*, location_id: int, department_name: str) -> str:
        sanitized = _SAFE_DEPT_RE.sub("-", department_name).strip("-").lower() or "department"
        return f"{sanitized}.{location_id}@{_DEFAULT_SEED_EMAIL_DOMAIN}"

    @staticmethod
    def _today_kst() -> date:
        return datetime.now(_KST).date()

