from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.core.codes import ErrorCode
from app.core.exceptions import BusinessException
from app.models.enum.ComplaintPetitionStatus import ComplaintPetitionStatus
from app.services.ComplaintPetitionService import ComplaintPetitionService


def _make_service(
    *,
    complaint_petition_repo: MagicMock | None = None,
) -> ComplaintPetitionService:
    return ComplaintPetitionService(
        complaint_email_service=MagicMock(),
        issue_pin_repo=MagicMock(),
        location_department_repo=MagicMock(),
        complaint_petition_repo=complaint_petition_repo or MagicMock(),
        department_repo=MagicMock(),
        location_repo=MagicMock(),
        user_repo=MagicMock(),
        s3_util=MagicMock(),
    )


def _make_petition_row() -> MagicMock:
    created_at = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)
    petition = MagicMock()
    petition.petition_id = 42
    petition.issue_pin_id = 7
    petition.location_department_id = 3
    petition.generated_on = date(2026, 6, 16)
    petition.pdf_s3_key = "issue-pdf/petition-7.pdf"
    petition.pdf_s3_url = "https://example.com/petition-7.pdf"
    petition.email_subject = "[민원] 테스트 제목"
    petition.email_body = "테스트 본문"
    petition.reliability_score = 0.85
    petition.reliability_basis = "검증 근거"
    petition.status = ComplaintPetitionStatus.CREATED.value
    petition.created_at = created_at
    petition.updated_at = None

    department = MagicMock()
    department.department_name = "도로"
    location = MagicMock()
    location.region = "서울특별시 강남구"
    location_department = MagicMock()
    location_department.location_id = 11
    location_department.location_department_email = "road@example.com"
    location_department.department = department
    location_department.location = location
    petition.location_department = location_department

    pin = MagicMock()
    pin.pin_title = "보도블록 파손"
    issue_pin = MagicMock()
    issue_pin.pin = pin
    petition.issue_pin = issue_pin
    return petition


class ComplaintPetitionReviewServiceTest(unittest.IsolatedAsyncioTestCase):
    def test_to_review_item_maps_joined_fields(self) -> None:
        service = _make_service()
        petition = _make_petition_row()

        item = service._to_review_item(petition)

        self.assertEqual(item.petition_id, 42)
        self.assertEqual(item.issue_pin_id, 7)
        self.assertEqual(item.location_id, 11)
        self.assertEqual(item.department_name, "도로")
        self.assertEqual(item.location_department_email, "road@example.com")
        self.assertEqual(item.generated_on, "2026-06-16")
        self.assertEqual(item.email_subject, "[민원] 테스트 제목")
        self.assertEqual(item.status, ComplaintPetitionStatus.CREATED.value)
        self.assertEqual(item.location_region, "서울특별시 강남구")
        self.assertEqual(item.pin_title, "보도블록 파손")

    async def test_get_for_review_raises_not_found(self) -> None:
        repo = MagicMock()
        repo.get_by_petition_id_for_review = AsyncMock(return_value=None)
        service = _make_service(complaint_petition_repo=repo)

        with self.assertRaises(BusinessException) as ctx:
            await service.get_for_review(999)

        self.assertEqual(ctx.exception.error_code, ErrorCode.NOT_FOUND)

    async def test_list_for_review_returns_paginated_items(self) -> None:
        petition = _make_petition_row()
        repo = MagicMock()
        repo.list_for_admin = AsyncMock(return_value=([petition], 1))
        service = _make_service(complaint_petition_repo=repo)

        result = await service.list_for_review(status=ComplaintPetitionStatus.CREATED.value, limit=20, offset=0)

        repo.list_for_admin.assert_awaited_once_with(
            status=ComplaintPetitionStatus.CREATED.value,
            limit=20,
            offset=0,
        )
        self.assertEqual(result.total, 1)
        self.assertEqual(result.limit, 20)
        self.assertEqual(result.offset, 0)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].petition_id, 42)
