"""Re-export for backward-compatible imports (deps, IssueService)."""

from app.services.internal.ai.ComplaintEmailVLMService import (
    ComplaintEmailVlmResultProcessor,
    ComplaintEmailVlmService,
)

__all__ = [
    "ComplaintEmailVlmResultProcessor",
    "ComplaintEmailVlmService",
]
