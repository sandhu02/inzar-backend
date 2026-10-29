import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.core.errors import RateLimitExceededError


class BaseRateLimiter(ABC):
    @abstractmethod
    async def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int, int]:
        """Returns (is_allowed, remaining_requests, reset_seconds)."""
        pass

    async def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        allowed, remaining, reset = await self.is_allowed(key, max_requests, window_seconds)
        if not allowed:
            raise RateLimitExceededError(
                message=f"Rate limit exceeded. Try again in {reset} seconds.",
                details={"retry_after_seconds": reset, "remaining": remaining},
            )


class InMemoryRateLimiter(BaseRateLimiter):
    def __init__(self) -> None:
        # Map of key -> list of timestamps
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def is_allowed(
        self, key: str, max_requests: int, window_seconds: int
    ) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - window_seconds

        # Clean old timestamps
        history = [ts for ts in self._requests[key] if ts > window_start]
        self._requests[key] = history

        if len(history) >= max_requests:
            oldest = history[0]
            retry_after = max(1, int(oldest + window_seconds - now))
            return False, 0, retry_after

        self._requests[key].append(now)
        remaining = max_requests - len(self._requests[key])
        return True, remaining, window_seconds

    def reset(self) -> None:
        self._requests.clear()


# Global in-memory rate limiter instance
rate_limiter = InMemoryRateLimiter()


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def rate_limit(
    max_requests: int,
    window_seconds: int,
    key_prefix: str = "rl",
) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        from app.core.config import settings

        if not settings.RATE_LIMIT_ENABLED:
            return

        # Key strategy: User ID if authenticated in state, else client IP
        user_id = getattr(request.state, "user_id", None)
        identity = f"user:{user_id}" if user_id else f"ip:{get_client_ip(request)}"
        key = f"{key_prefix}:{request.url.path}:{identity}"

        await rate_limiter.check(key=key, max_requests=max_requests, window_seconds=window_seconds)

    return dependency
