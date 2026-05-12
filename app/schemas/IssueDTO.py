from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IssueAnalysisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    content: str
    reliability: float
