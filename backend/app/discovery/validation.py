"""Candidate validation for web-discovered properties.

Validates a :class:`PropertyCandidate` before it is persisted. Missing optional
fields are fine; malformed/impossible values or unsafe URLs are not.
"""
from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.discovery.models import PropertyCandidate
from app.providers.web_search.security import validate_result_url

_MAX_TITLE_LENGTH = 500
_MAX_DESCRIPTION_LENGTH = 10_000
_MAX_ABSURD_PRICE = 5_000_000_000  # > ₹500 Cr → almost certainly a parse error
_MAX_ABSURD_AREA = 100_000_000     # > 100M sqft → almost certainly a parse error


class CandidateValidationError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def validate_candidate(candidate: PropertyCandidate) -> list[str]:
    """Return a list of blocking problems (empty = valid)."""
    problems: list[str] = []

    if not candidate.title or len(candidate.title) > _MAX_TITLE_LENGTH:
        problems.append("missing or oversized title")
    if candidate.description and len(candidate.description) > _MAX_DESCRIPTION_LENGTH:
        problems.append("oversized description")
    if not candidate.url:
        problems.append("missing url")
    else:
        try:
            validate_result_url(candidate.url)
        except Exception:
            problems.append("unsafe url")
    if not candidate.source_domain:
        problems.append("missing source domain")

    if candidate.price is not None:
        if candidate.price < 0:
            problems.append("negative price")
        elif candidate.price > _MAX_ABSURD_PRICE:
            problems.append("implausible price")
    if candidate.bedrooms is not None and not (0 <= candidate.bedrooms <= 20):
        problems.append("implausible bedrooms")
    if candidate.bathrooms is not None and not (0 <= candidate.bathrooms <= 20):
        problems.append("implausible bathrooms")
    if candidate.area is not None:
        if candidate.area <= 0:
            problems.append("non-positive area")
        elif candidate.area > _MAX_ABSURD_AREA:
            problems.append("implausible area")
    if candidate.transaction_type not in (None, "rent", "sale"):
        problems.append("invalid transaction type")
    if candidate.currency and len(candidate.currency) != 3:
        problems.append("invalid currency")

    if candidate.confidence < settings.WEB_DISCOVERY_MIN_CONFIDENCE:
        problems.append("low extraction confidence")
    return problems


def is_valid(candidate: PropertyCandidate) -> bool:
    return not validate_candidate(candidate)


def assert_valid(candidate: PropertyCandidate) -> PropertyCandidate:
    """Validate or raise :class:`CandidateValidationError` (used by the pipeline)."""
    problems = validate_candidate(candidate)
    if problems:
        raise CandidateValidationError(problems)
    return candidate