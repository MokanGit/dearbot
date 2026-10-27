import re
import time
from typing import Dict, List
from collections import Counter, defaultdict
from fastapi import HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.models import Interaction, Application
from backend.app.config import settings

# Limits
MAX_QUESTION_LENGTH = 2500  # Approx 500 tokens
MAX_QUESTIONS_PER_APPLICATION = settings.MAX_QUESTIONS_PER_APPLICATION
MAX_PER_MINUTE = settings.MAX_QUESTIONS_PER_MINUTE_PER_IP
MAX_PER_HOUR = settings.MAX_QUESTIONS_PER_HOUR_PER_IP

# Zero-width, invisible and control characters regex
ZERO_WIDTH_CHARS = re.compile(
    r'[\u200B-\u200D\uFEFF\u200E\u200F\u00AD\u202A-\u202E\u0000-\u0008\u000B\u000C\u000E-\u001F]'
)


def validate_and_sanitize_question(raw_question: str) -> str:
    """
    Validates question length, strips invisible/zero-width unicode characters,
    and protects against context-stuffing and repetition abuse.
    """
    if not raw_question or not raw_question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Strip zero-width, invisible formatting and control characters
    cleaned = ZERO_WIDTH_CHARS.sub("", raw_question)

    # 2. Enforce character limit (2500 characters ≈ 500 tokens)
    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question exceeds maximum allowed length of {MAX_QUESTION_LENGTH} characters (~500 tokens). Current length: {len(cleaned)}."
        )

    # 3. Context Stuffing Defense: Check for excessively long single tokens (gibberish/base64 stuffing)
    words = cleaned.split()
    if any(len(w) > 120 for w in words):
        raise HTTPException(
            status_code=400,
            detail="Potential context-stuffing detected: excessively long token without whitespace."
        )

    # 4. Context Stuffing Defense: Check for character repetition chains (e.g. 'aaaaa...' > 35 chars)
    if re.search(r"(.)\1{35,}", cleaned):
        raise HTTPException(
            status_code=400,
            detail="Potential context-stuffing detected: abnormal repeated character sequence."
        )

    # 5. Context Stuffing Defense: Check for excessive word repetition (e.g. same word > 15 times and > 35% of total)
    if len(words) >= 12:
        lower_words = [w.lower().strip(".,!?;:\"'()") for w in words if len(w) > 2]
        if lower_words:
            counts = Counter(lower_words)
            most_common_word, highest_count = counts.most_common(1)[0]
            if highest_count >= 15 and (highest_count / len(words)) > 0.35:
                raise HTTPException(
                    status_code=400,
                    detail=f"Potential context-stuffing detected: word '{most_common_word}' repeated {highest_count} times."
                )

    # 6. Normalize whitespaces
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    return cleaned


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter per IP for AI queries and general access."""

    def __init__(self):
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._general_requests: Dict[str, List[float]] = defaultdict(list)

    def check_rate_limit(self, client_ip: str):
        now = time.time()
        window_1m = now - 60.0
        window_1h = now - 3600.0

        # Prune older records for this IP
        history = [t for t in self._requests[client_ip] if t > window_1h]
        self._requests[client_ip] = history

        # Check 1-minute limit
        count_1m = sum(1 for t in history if t > window_1m)
        if count_1m >= MAX_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests. Rate limit of {MAX_PER_MINUTE} questions/minute exceeded. Please wait.",
                headers={"Retry-After": "60"}
            )

        # Check 1-hour limit
        if len(history) >= MAX_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail=f"Hourly question limit ({MAX_PER_HOUR} questions/hour) exceeded. Please try again later.",
                headers={"Retry-After": "300"}
            )

        # Record current request
        self._requests[client_ip].append(now)

    def check_general_rate_limit(
        self,
        client_ip: str,
        max_per_minute: int = settings.MAX_VIEWS_PER_MINUTE_PER_IP,
        max_per_hour: int = settings.MAX_VIEWS_PER_HOUR_PER_IP,
    ):
        now = time.time()
        window_1m = now - 60.0
        window_1h = now - 3600.0

        history = [t for t in self._general_requests[client_ip] if t > window_1h]
        self._general_requests[client_ip] = history

        count_1m = sum(1 for t in history if t > window_1m)
        if count_1m >= max_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Too many view/download requests ({max_per_minute}/minute limit exceeded). Please wait.",
                headers={"Retry-After": "60"}
            )

        if len(history) >= max_per_hour:
            raise HTTPException(
                status_code=429,
                detail=f"Hourly view/download limit ({max_per_hour}/hour limit exceeded). Please try again later.",
                headers={"Retry-After": "300"}
            )

        self._general_requests[client_ip].append(now)


rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    """Extract a client IP, trusting forwarding headers only when configured."""
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else "unknown"


QUESTION_EVENT_TYPES = ["QUESTION", "QUESTION_GET", "WEBMCP_CALL", "MCP_CALL"]


async def verify_application_quota(app: Application, session: AsyncSession):
    """
    Verifies that the application has not exceeded its maximum question quota
    across all supported channels (REST POST, URL GET, WebMCP, and MCP).
    """
    stmt = select(func.count(Interaction.id)).where(
        Interaction.application_id == app.id,
        Interaction.event_type.in_(QUESTION_EVENT_TYPES)
    )
    result = await session.execute(stmt)
    count = result.scalar() or 0

    if count >= MAX_QUESTIONS_PER_APPLICATION:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Frågekvoten för denna profil har uppnåtts (max {MAX_QUESTIONS_PER_APPLICATION} frågor). "
                f"Vänligen kontakta {settings.CANDIDATE_NAME} direkt för vidare dialog."
            )
        )
