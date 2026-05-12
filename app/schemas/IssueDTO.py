from __future__ import annotations

from fastapi import UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.models.enum.ToneType import ToneType


class CreateIssuePinRequest(BaseModel):
    title: str
    content: str
    tone: ToneType = ToneType.NONE
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ImageWithLocation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: UploadFile
    address: str | None = None


class IssueAnalysisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    content: str
    reliability: float
