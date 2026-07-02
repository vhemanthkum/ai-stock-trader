"""
Async Token Bucket Rate Limiter for multi-provider LLM routing.

Replaces naive `asyncio.sleep(4.0)` with a proper per-provider limiter
that tracks calls per minute AND per day.

Usage:
    limiter = ProviderRateLimiter()
    await limiter.acquire("google")   # blocks until safe to call
    await limiter.acquire("groq")     # independent bucket
    await limiter.acquire("ollama")   # unlimited, never blocks
"""

import asyncio
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class ProviderRateLimiter:
    """
    Per-provider rate limiter using token bucket algorithm.

    Each provider has independent RPM (requests per minute) and
    RPD (requests per day) limits. The limiter blocks the caller
    until the next request is safe to send.

    Ollama (local) has no limits and never blocks.
    """

    # Default limits per provider
    DEFAULT_LIMITS = {
        "google":     {"rpm": 15, "rpd": 1500},
        "groq":       {"rpm": 30, "rpd": 1000},
        "openrouter": {"rpm": 20, "rpd": 200},
        "nvidia":     {"rpm": 60, "rpd": 1000},
        "anthropic":  {"rpm": 5,  "rpd": 50},
        "ollama":     {"rpm": 999, "rpd": 99999},  # Unlimited
    }

    def __init__(self, custom_limits: dict | None = None):
        self._limits = {**self.DEFAULT_LIMITS}
        if custom_limits:
            self._limits.update(custom_limits)

        # Track timestamps of recent calls per provider
        self._minute_calls: dict[str, list[float]] = defaultdict(list)
        self._day_calls: dict[str, int] = defaultdict(int)
        self._day_start: float = time.time()

        # Lock to prevent concurrent acquire races
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, provider: str) -> None:
        """
        Wait until it's safe to call the given provider.

        This method is the ONLY rate-limiting mechanism in the system.
        Remove all `asyncio.sleep(X)` calls from agents and main.py.
        """
        if provider == "ollama":
            return  # Local model — no limits

        async with self._locks[provider]:
            limits = self._limits.get(provider, {"rpm": 10, "rpd": 500})
            rpm = limits["rpm"]
            rpd = limits["rpd"]

            # Reset daily counter if 24h elapsed
            if time.time() - self._day_start > 86400:
                self._day_calls.clear()
                self._day_start = time.time()

            if self._day_calls[provider] >= rpd:
                logger.error(
                    f"[RateLimiter] {provider} daily limit ({rpd}) exhausted. "
                    f"Cannot make more calls today."
                )
                from utils.exceptions import RateLimitExhaustedError
                raise RateLimitExhaustedError(provider, rpd)

            # Clean old timestamps (older than 60s)
            now = time.time()
            self._minute_calls[provider] = [
                t for t in self._minute_calls[provider] if now - t < 60
            ]

            # Wait if at RPM limit
            while len(self._minute_calls[provider]) >= rpm:
                oldest = self._minute_calls[provider][0]
                wait_time = 60 - (now - oldest) + 0.1  # small buffer
                if wait_time > 0:
                    logger.info(
                        f"[RateLimiter] {provider} at RPM limit ({rpm}/min). "
                        f"Waiting {wait_time:.1f}s..."
                    )
                    await asyncio.sleep(wait_time)
                now = time.time()
                self._minute_calls[provider] = [
                    t for t in self._minute_calls[provider] if now - t < 60
                ]

            # Record this call
            self._minute_calls[provider].append(time.time())
            self._day_calls[provider] += 1

    def get_usage(self, provider: str) -> dict:
        """Get current usage stats for a provider."""
        limits = self._limits.get(provider, {"rpm": 0, "rpd": 0})
        now = time.time()
        recent = [t for t in self._minute_calls[provider] if now - t < 60]
        return {
            "provider": provider,
            "calls_last_minute": len(recent),
            "rpm_limit": limits["rpm"],
            "calls_today": self._day_calls[provider],
            "rpd_limit": limits["rpd"],
        }

    def get_all_usage(self) -> list[dict]:
        """Get usage stats for all providers."""
        return [
            self.get_usage(p) for p in self._limits
            if self._day_calls[p] > 0
        ]


# Global singleton — shared across all agents
_global_limiter: ProviderRateLimiter | None = None


def get_rate_limiter() -> ProviderRateLimiter:
    """Get the global rate limiter singleton."""
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = ProviderRateLimiter()
    return _global_limiter
