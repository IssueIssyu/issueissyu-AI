from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImageSnapshot:
    data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class IssuePinReliabilityJob:
    issue_pin_id: int
    pin_id: int
    title: str
    content: str
    user_gps: str
    user_address: str | None
