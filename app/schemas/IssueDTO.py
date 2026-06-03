from __future__ import annotations

from enum import StrEnum

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.models.enum.ToneType import ToneType


class ReliabilityStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageUploadStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateIssuePinRequest(BaseModel):
    title: str
    content: str
    tone: ToneType = ToneType.NONE
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class UpdateIssuePinImageUrlItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin_image_url: str = Field(alias="pinImageUrl")
    is_main: bool = Field(alias="isMain")


class PinImageIsMainItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    is_main: bool = Field(alias="isMain")


UpdateIssuePinNewImageItem = PinImageIsMainItem


class CreateIssuePinMultipartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    pin_title: str = Field(alias="pinTitle")
    pin_content: str = Field(alias="pinContent")
    pin_images: list[PinImageIsMainItem] = Field(alias="pinImages")


class UpdateIssuePinMultipartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin_title: str = Field(alias="pinTitle")
    pin_content: str = Field(alias="pinContent")
    pin_image_urls: list[UpdateIssuePinImageUrlItem] | None = Field(
        default=None,
        alias="pinImageUrls",
    )
    pin_images: list[PinImageIsMainItem] | None = Field(
        default=None,
        alias="pinImages",
    )


class ImageWithLocation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: UploadFile
    address: str | None = None


class IssueAnalysisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    content: str


class IssuePinAiQuotaResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    enabled: bool
    daily_limit: int = Field(serialization_alias="dailyLimit")
    used_count: int = Field(serialization_alias="usedCount")
    remaining_count: int = Field(serialization_alias="remainingCount")
    reset_at: str = Field(serialization_alias="resetAt")


class CreateIssuePinResponse(BaseModel):
    pin_id: int
    issue_pin_id: int
    reliability_status: ReliabilityStatus = ReliabilityStatus.PENDING
    image_upload_status: ImageUploadStatus


class IssuePinImageItem(BaseModel):
    pin_image_id: int
    url: str
    is_main: bool


class IssuePinDetailResponse(BaseModel):
    pin_id: int
    issue_pin_id: int
    title: str
    content: str
    tone: ToneType
    issue_pin_state: str
    issue_confidence: float | None
    confidence_content: str | None
    reliability_status: ReliabilityStatus
    image_upload_status: ImageUploadStatus
    images: list[IssuePinImageItem]


class IssuePinHomeImageItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pin_image_id: int = Field(serialization_alias="pinImageId")
    pin_image_url: str = Field(serialization_alias="pinImageUrl")
    is_main: bool = Field(serialization_alias="isMain")


class IssuePinHomeDetailResponse(BaseModel):
    """핀 상세 홈 응답 (조회·게시 공통)."""

    model_config = ConfigDict(populate_by_name=True)

    issue_pin_id: int = Field(serialization_alias="issuePinId")
    pin_id: int = Field(serialization_alias="pinId")
    pin_type: str = Field(serialization_alias="pinType")
    pin_title: str = Field(serialization_alias="pinTitle")
    pin_content: str = Field(serialization_alias="pinContent")
    issue_pin_state: str = Field(serialization_alias="issuePinState")
    pin_detail_address: str | None = Field(serialization_alias="pinDetailAddress")
    like_count: int = Field(serialization_alias="likeCount")
    is_like: bool = Field(serialization_alias="isLike")
    pin_user_id: str = Field(serialization_alias="pinUserId")
    pin_user_profile: str | None = Field(serialization_alias="pinUserProfile")
    pin_user_nickname: str | None = Field(serialization_alias="pinUserNickname")
    pin_image_urls: list[IssuePinHomeImageItem] = Field(serialization_alias="pinImageUrls")
    discount: None = None
    store_image_url: None = Field(default=None, serialization_alias="storeImageUrl")
    is_updated: bool = Field(serialization_alias="isUpdated")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str | None = Field(serialization_alias="updatedAt")
    view: int
    is_reported: bool = Field(serialization_alias="isReported")
    is_mine: bool = Field(serialization_alias="isMine")
    community_id: int | None = Field(serialization_alias="communityId")
    reliability_status: ReliabilityStatus = Field(serialization_alias="reliabilityStatus")
    image_upload_status: ImageUploadStatus = Field(serialization_alias="imageUploadStatus")


class IssuePinReliabilityResponse(BaseModel):
    """이슈 핀 신뢰도 전용 조회 응답."""

    model_config = ConfigDict(populate_by_name=True)

    issue_pin_id: int = Field(serialization_alias="issuePinId")
    pin_id: int = Field(serialization_alias="pinId")
    issue_confidence: float | None = Field(serialization_alias="issueConfidence")
    confidence_content: str | None = Field(serialization_alias="confidenceContent")
    reliability_status: ReliabilityStatus = Field(serialization_alias="reliabilityStatus")
    image_upload_status: ImageUploadStatus = Field(serialization_alias="imageUploadStatus")
