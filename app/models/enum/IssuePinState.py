from __future__ import annotations

from enum import StrEnum


class IssuePinState(StrEnum):
    BEFORE_PROGRESS = "BEFORE_PROGRESS"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
