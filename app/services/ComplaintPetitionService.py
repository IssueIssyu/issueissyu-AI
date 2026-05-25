from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, date
from email.message import EmailMessage
import io
import logging
import re
import smtplib
import ssl
from typing import Sequence
from zoneinfo import ZoneInfo

import certifi
from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from app.core.codes import ErrorCode
from app.core.config import settings
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
_S3_PDF_PREFIX = "issue-pdf"
_DEFAULT_SEED_EMAIL_DOMAIN = "placeholder.local"
_SAFE_DEPT_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
_DEFAULT_TARGET_PETITION = 30


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

        pin = issue_pin.pin
        pin_location = pin.pin_location
        if pin_location is None:
            raise_business_exception(ErrorCode.VALIDATION_ERROR, "핀 위치 정보가 없습니다.")
        location_id = pin_location.location_id
        if enforce_threshold:
            target_petition = await self._target_petition_for_location(location_id=location_id)
            if issue_pin.petition_count < target_petition:
                raise_business_exception(
                    ErrorCode.VALIDATION_ERROR,
                    f"petition_count가 target_petition({target_petition}) 미만이라 자동 생성 대상이 아닙니다.",
                )

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
            submitter_name=(pin.user.user_name if pin.user is not None else None),
            submitter_address=pin_location.detail_address,
            submitter_phone=(pin.user.phone if pin.user is not None else None),
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

    async def create_scheduled_petitions(self, *, default_threshold: int = _DEFAULT_TARGET_PETITION) -> dict[str, int]:
        generated_on = self._today_kst()
        offset = 0
        batch_size = 100
        success_count = 0
        skip_count = 0
        fail_count = 0

        while True:
            rows = await self.issue_pin_repo.list_by_target_petition(
                default_threshold=default_threshold,
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
        send_targets: list[ComplaintPetition] = []

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

            send_targets.append(petition)

        send_results = await self._send_many_limited(send_targets)

        for petition in send_targets:
            send_ok, reason = send_results.get(petition.petition_id, (False, "송신 결과를 확인할 수 없습니다."))
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

    async def _send_many_limited(
        self,
        petitions: Sequence[ComplaintPetition],
    ) -> dict[int, tuple[bool, str | None]]:
        if not petitions:
            return {}

        concurrency = max(1, int(settings.smtp_send_concurrency))
        semaphore = asyncio.Semaphore(concurrency)
        results: dict[int, tuple[bool, str | None]] = {}

        async def _run_one(petition: ComplaintPetition) -> None:
            async with semaphore:
                results[petition.petition_id] = await self._send_one(petition)

        await asyncio.gather(*(_run_one(petition) for petition in petitions))
        return results

    async def _send_one(self, petition: ComplaintPetition) -> tuple[bool, str | None]:
        recipient = petition.location_department.location_department_email.strip()
        if not recipient:
            return False, "부서 이메일이 비어 있습니다."

        smtp_host = (settings.smtp_host or "").strip()
        smtp_username = (settings.smtp_username or "").strip()
        smtp_from_email = (settings.smtp_from_email or "").strip() or smtp_username
        smtp_password = (
            settings.smtp_password.get_secret_value()
            if settings.smtp_password is not None
            else ""
        )
        if not smtp_host:
            return False, "SMTP_HOST 설정이 필요합니다."
        if not smtp_from_email:
            return False, "SMTP_FROM_EMAIL 또는 SMTP_USERNAME 설정이 필요합니다."
        if settings.smtp_use_tls and settings.smtp_use_ssl:
            return False, "SMTP_USE_TLS와 SMTP_USE_SSL을 동시에 사용할 수 없습니다."

        msg = EmailMessage()
        msg["Subject"] = petition.email_subject
        msg["From"] = smtp_from_email
        msg["To"] = recipient
        msg.set_content(petition.email_body)

        try:
            pdf_bytes, content_type = await self.s3_util.download_binary(petition.pdf_s3_key)
        except Exception as exc:
            logger.exception("PDF 첨부 다운로드 실패 petition_id=%s", petition.petition_id)
            return False, f"PDF 다운로드 실패: {exc}"

        if not pdf_bytes:
            return False, "PDF 데이터가 비어 있습니다."

        subtype = "pdf"
        if "/" in content_type:
            candidate = content_type.split("/", maxsplit=1)[1].strip().lower()
            if candidate:
                subtype = candidate
        filename = self._build_pretty_attachment_filename(petition)
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype=subtype,
            filename=filename,
        )

        try:
            tls_context = ComplaintPetitionService._build_smtp_ssl_context()
            await run_in_threadpool(
                ComplaintPetitionService._send_smtp_message_blocking,
                smtp_host,
                settings.smtp_port,
                settings.smtp_timeout_seconds,
                settings.smtp_use_ssl,
                settings.smtp_use_tls,
                smtp_username,
                smtp_password,
                msg,
                tls_context,
            )
        except Exception as exc:
            logger.exception("SMTP 송신 실패 petition_id=%s", petition.petition_id)
            return False, f"SMTP 송신 실패: {exc}"

        return True, None

    @staticmethod
    def _build_smtp_ssl_context() -> ssl.SSLContext:
        context = ssl.create_default_context(cafile=certifi.where())
        if settings.smtp_skip_cert_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        return context

    @staticmethod
    def _send_smtp_message_blocking(
        smtp_host: str,
        smtp_port: int,
        smtp_timeout_seconds: float,
        smtp_use_ssl: bool,
        smtp_use_tls: bool,
        smtp_username: str,
        smtp_password: str,
        msg: EmailMessage,
        tls_context: ssl.SSLContext,
    ) -> None:
        if smtp_use_ssl:
            with smtplib.SMTP_SSL(
                host=smtp_host,
                port=smtp_port,
                timeout=smtp_timeout_seconds,
                context=tls_context,
            ) as client:
                if smtp_username:
                    client.login(smtp_username, smtp_password)
                client.send_message(msg)
            return

        with smtplib.SMTP(
            host=smtp_host,
            port=smtp_port,
            timeout=smtp_timeout_seconds,
        ) as client:
            client.ehlo()
            if smtp_use_tls:
                client.starttls(context=tls_context)
                client.ehlo()
            if smtp_username:
                client.login(smtp_username, smtp_password)
            client.send_message(msg)

    @staticmethod
    def _build_pretty_attachment_filename(petition: ComplaintPetition) -> str:
        date_text = petition.generated_on.isoformat() if petition.generated_on else "unknown-date"
        category = (
            petition.location_department.department.department_name
            if petition.location_department is not None and petition.location_department.department is not None
            else "category"
        )
        category = (category or "category").strip()
        category = re.sub(r"\s+", "", category)
        category = re.sub(r'[\\/:*?"<>|]+', "-", category).strip("-") or "category"
        return f"민원의견서_{date_text}_{category}_issue{petition.issue_pin_id}.pdf"

    async def _target_petition_for_location(self, *, location_id: int) -> int:
        if location_id <= 0:
            return _DEFAULT_TARGET_PETITION
        target = await self.location_repo.get_target_petition_by_location_id(location_id=location_id)
        if target is None:
            return _DEFAULT_TARGET_PETITION
        return max(1, int(target))

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

