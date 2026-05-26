from __future__ import annotations

from enum import StrEnum


class ComplaintPetitionStatus(StrEnum):
    CREATED = "CREATED"
    SENT = "SENT"
    FAILED = "FAILED"

