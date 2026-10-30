from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel


class ReviewDecision(BaseModel):
    decision: Literal["approved", "needs_review", "rejected"]
    reason: str | None = None


class BaseReviewProvider(ABC):
    @abstractmethod
    async def review(
        self,
        incident_data: dict[str, Any],
        category_data: dict[str, Any],
        review_mode: str = "auto_approve",
    ) -> ReviewDecision:
        """Evaluate incident and return a ReviewDecision."""
        pass


class StubReviewProvider(BaseReviewProvider):
    async def review(
        self,
        incident_data: dict[str, Any],
        category_data: dict[str, Any],
        review_mode: str = "auto_approve",
    ) -> ReviewDecision:
        # If category explicitly mandates manual review, prioritize that
        if category_data.get("require_manual_review", False):
            return ReviewDecision(
                decision="needs_review",
                reason="Category requires mandatory moderator review",
            )

        # Respect the global review_mode
        if review_mode == "manual":
            return ReviewDecision(
                decision="needs_review",
                reason="System set to manual review mode",
            )

        # Default auto_approve mode
        return ReviewDecision(
            decision="approved",
            reason="Auto-approved by default policy",
        )


class FakeReviewProvider(BaseReviewProvider):
    def __init__(
        self,
        default_decision: Literal["approved", "needs_review", "rejected"] = "approved",
        fail_with_error: bool = False,
    ) -> None:
        self.default_decision = default_decision
        self.fail_with_error = fail_with_error

    async def review(
        self,
        incident_data: dict[str, Any],
        category_data: dict[str, Any],
        review_mode: str = "auto_approve",
    ) -> ReviewDecision:
        if self.fail_with_error:
            raise RuntimeError("Review provider service unavailable")
        return ReviewDecision(decision=self.default_decision, reason="Fake review decision")


def get_review_provider() -> BaseReviewProvider:
    return StubReviewProvider()
