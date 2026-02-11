"""Metrics and observability module for JARVIS MK1 Lite.

This module provides application metrics, health checks, and observability features.
Follows KISS principle with simple in-memory counters suitable for single-instance deployment.
Thread-safe for concurrent async operations using asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Global lock for thread-safe metrics operations
_metrics_lock: asyncio.Lock | None = None


def _get_metrics_lock() -> asyncio.Lock:
    """Get or create the global metrics lock.

    Returns:
        The asyncio.Lock for metrics operations.
    """
    global _metrics_lock
    if _metrics_lock is None:
        _metrics_lock = asyncio.Lock()
    return _metrics_lock


def _create_ordered_dict() -> OrderedDict[int, int]:
    """Factory function for creating OrderedDict with proper typing."""
    return OrderedDict()


@dataclass
class Metrics:
    """Application metrics storage.

    Tracks request counts, errors, latency, and per-user statistics.
    Uses simple in-memory storage suitable for single-instance deployment.
    User metrics use LRU cache to prevent unbounded memory growth.
    """

    # Request counters
    total_requests: int = 0
    total_errors: int = 0
    total_commands: int = 0
    total_messages: int = 0

    # Command counters
    command_counts: dict[str, int] = field(default_factory=dict)

    # Per-user counters with LRU eviction
    user_request_counts: OrderedDict[int, int] = field(default_factory=_create_ordered_dict)
    user_error_counts: OrderedDict[int, int] = field(default_factory=_create_ordered_dict)

    # Maximum number of users to track (LRU eviction when exceeded)
    max_tracked_users: int = 1000

    # Safety counters
    safety_checks: int = 0
    blocked_dangerous: int = 0
    blocked_critical: int = 0

    # Latency tracking (last 100 requests)
    latencies: list[float] = field(default_factory=list)
    max_latency_samples: int = 100

    # Timestamps
    start_time: float = field(default_factory=time.time)
    last_request_time: float | None = None

    def _evict_lru_users(self) -> None:
        """Evict least recently used users if over capacity."""
        while len(self.user_request_counts) > self.max_tracked_users:
            # Remove oldest (first) entry
            self.user_request_counts.popitem(last=False)
        while len(self.user_error_counts) > self.max_tracked_users:
            self.user_error_counts.popitem(last=False)

    def record_request(self, user_id: int, is_command: bool = False) -> None:
        """Record a request from a user (synchronous version).

        Args:
            user_id: Telegram user ID.
            is_command: Whether the request is a command (vs regular message).
        """
        self.total_requests += 1

        # Update user count with LRU behavior (move to end)
        count = self.user_request_counts.pop(user_id, 0) + 1
        self.user_request_counts[user_id] = count
        self._evict_lru_users()

        self.last_request_time = time.time()

        if is_command:
            self.total_commands += 1
        else:
            self.total_messages += 1

    async def record_request_async(self, user_id: int, is_command: bool = False) -> None:
        """Record a request from a user (async thread-safe version).

        Args:
            user_id: Telegram user ID.
            is_command: Whether the request is a command (vs regular message).
        """
        async with _get_metrics_lock():
            self.record_request(user_id, is_command)

    def record_command(self, command: str, user_id: int) -> None:
        """Record a specific command usage.

        Args:
            command: The command name (e.g., 'start', 'help').
            user_id: Telegram user ID.
        """
        self.command_counts[command] = self.command_counts.get(command, 0) + 1
        self.record_request(user_id, is_command=True)

    def record_error(self, user_id: int) -> None:
        """Record an error for a user (synchronous version).

        Args:
            user_id: Telegram user ID.
        """
        self.total_errors += 1

        # Update error count with LRU behavior (move to end)
        count = self.user_error_counts.pop(user_id, 0) + 1
        self.user_error_counts[user_id] = count
        self._evict_lru_users()

    async def record_error_async(self, user_id: int) -> None:
        """Record an error for a user (async thread-safe version).

        Args:
            user_id: Telegram user ID.
        """
        async with _get_metrics_lock():
            self.record_error(user_id)

    def record_latency(self, latency: float) -> None:
        """Record request latency (synchronous version).

        Args:
            latency: Latency in seconds.
        """
        self.latencies.append(latency)
        # Keep only last N samples
        if len(self.latencies) > self.max_latency_samples:
            self.latencies = self.latencies[-self.max_latency_samples :]

    async def record_latency_async(self, latency: float) -> None:
        """Record request latency (async thread-safe version).

        Args:
            latency: Latency in seconds.
        """
        async with _get_metrics_lock():
            self.record_latency(latency)

    def record_safety_check(self, is_dangerous: bool = False, is_critical: bool = False) -> None:
        """Record a safety check result.

        Args:
            is_dangerous: Whether a dangerous command was blocked.
            is_critical: Whether a critical command was blocked.
        """
        self.safety_checks += 1
        if is_dangerous:
            self.blocked_dangerous += 1
        if is_critical:
            self.blocked_critical += 1

    def get_uptime(self) -> float:
        """Get application uptime in seconds.

        Returns:
            Uptime in seconds since start.
        """
        return time.time() - self.start_time

    def get_average_latency(self) -> float:
        """Get average request latency.

        Returns:
            Average latency in seconds, or 0.0 if no samples.
        """
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    def get_p95_latency(self) -> float:
        """Get 95th percentile latency.

        Returns:
            P95 latency in seconds, or 0.0 if no samples.
        """
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]

    def get_error_rate(self) -> float:
        """Get error rate as percentage.

        Returns:
            Error rate percentage (0-100).
        """
        if self.total_requests == 0:
            return 0.0
        return (self.total_errors / self.total_requests) * 100

    def format_uptime(self) -> str:
        """Format uptime as human-readable string.

        Returns:
            Formatted uptime string (e.g., "1d 2h 30m 15s").
        """
        uptime = int(self.get_uptime())
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)

    def reset(self) -> None:
        """Reset all metrics to initial values."""
        self.total_requests = 0
        self.total_errors = 0
        self.total_commands = 0
        self.total_messages = 0
        self.command_counts.clear()
        self.user_request_counts.clear()
        self.user_error_counts.clear()
        self.safety_checks = 0
        self.blocked_dangerous = 0
        self.blocked_critical = 0
        self.latencies.clear()
        self.start_time = time.time()
        self.last_request_time = None


@dataclass
class HealthStatus:
    """Health check status.

    Represents the current health state of the application.
    """

    healthy: bool
    status: str
    uptime: float
    uptime_formatted: str
    total_requests: int
    error_rate: float
    avg_latency: float
    claude_healthy: bool | None = None  # None if not checked


@dataclass
class RateLimiter:
    """Simple token bucket rate limiter.

    Limits requests per user using a token bucket algorithm.
    Each user gets a bucket that refills over time.
    """

    # Maximum tokens per bucket
    max_tokens: int = 10

    # Refill rate (tokens per second)
    refill_rate: float = 0.5

    # User buckets: user_id -> (tokens, last_update_time)
    buckets: dict[int, tuple[float, float]] = field(default_factory=dict)

    def _get_bucket(self, user_id: int) -> tuple[float, float]:
        """Get or create a bucket for a user.

        Args:
            user_id: Telegram user ID.

        Returns:
            Tuple of (current_tokens, last_update_time).
        """
        if user_id not in self.buckets:
            self.buckets[user_id] = (float(self.max_tokens), time.time())
        return self.buckets[user_id]

    def _refill_bucket(self, user_id: int) -> float:
        """Refill a user's bucket based on time elapsed.

        Args:
            user_id: Telegram user ID.

        Returns:
            Current token count after refill.
        """
        tokens, last_update = self._get_bucket(user_id)
        now = time.time()
        elapsed = now - last_update

        # Add tokens based on elapsed time
        new_tokens = min(self.max_tokens, tokens + elapsed * self.refill_rate)
        self.buckets[user_id] = (new_tokens, now)

        return new_tokens

    def is_allowed(self, user_id: int, cost: float = 1.0) -> bool:
        """Check if a request is allowed and consume tokens.

        Args:
            user_id: Telegram user ID.
            cost: Token cost for this request (default 1.0).

        Returns:
            True if request is allowed, False if rate limited.
        """
        tokens = self._refill_bucket(user_id)

        if tokens >= cost:
            # Consume tokens
            _, last_update = self.buckets[user_id]
            self.buckets[user_id] = (tokens - cost, last_update)
            return True

        return False

    def get_remaining(self, user_id: int) -> float:
        """Get remaining tokens for a user.

        Args:
            user_id: Telegram user ID.

        Returns:
            Number of tokens remaining.
        """
        return self._refill_bucket(user_id)

    def get_retry_after(self, user_id: int, cost: float = 1.0) -> float:
        """Get seconds until next request will be allowed.

        Args:
            user_id: Telegram user ID.
            cost: Token cost for the request.

        Returns:
            Seconds until request will be allowed, or 0 if already allowed.
        """
        tokens = self._refill_bucket(user_id)

        if tokens >= cost:
            return 0.0

        # Calculate time needed to accumulate enough tokens
        needed = cost - tokens
        return needed / self.refill_rate

    def reset_user(self, user_id: int) -> None:
        """Reset a user's bucket to full.

        Args:
            user_id: Telegram user ID.
        """
        self.buckets[user_id] = (float(self.max_tokens), time.time())

    def reset_all(self) -> None:
        """Reset all user buckets."""
        self.buckets.clear()


# Global instances
metrics = Metrics()
rate_limiter = RateLimiter()


def get_health_status(claude_healthy: bool | None = None) -> HealthStatus:
    """Get current application health status.

    Args:
        claude_healthy: Optional Claude CLI health status.

    Returns:
        HealthStatus with current metrics.
    """
    return HealthStatus(
        healthy=metrics.get_error_rate() < 10.0,  # Healthy if < 10% error rate
        status="healthy" if metrics.get_error_rate() < 10.0 else "degraded",
        uptime=metrics.get_uptime(),
        uptime_formatted=metrics.format_uptime(),
        total_requests=metrics.total_requests,
        error_rate=metrics.get_error_rate(),
        avg_latency=metrics.get_average_latency(),
        claude_healthy=claude_healthy,
    )


def format_metrics_message(session_stats: dict[str, int | float | None] | None = None) -> str:
    """Format metrics as a Telegram message.

    Args:
        session_stats: Optional session statistics from ClaudeBridge.get_session_stats().

    Returns:
        Formatted metrics string for Telegram.
    """
    health = get_health_status()

    # Build base metrics message
    message = f"""*Application Metrics*

*Status:* {"+" if health.healthy else "-"} {health.status.upper()}
*Uptime:* `{health.uptime_formatted}`

*Requests:*
- Total: `{metrics.total_requests}`
- Commands: `{metrics.total_commands}`
- Messages: `{metrics.total_messages}`
- Errors: `{metrics.total_errors}`
- Error Rate: `{health.error_rate:.1f}%`

*Latency:*
- Average: `{metrics.get_average_latency()*1000:.0f}ms`
- P95: `{metrics.get_p95_latency()*1000:.0f}ms`

*Safety:*
- Total Checks: `{metrics.safety_checks}`
- Blocked Dangerous: `{metrics.blocked_dangerous}`
- Blocked Critical: `{metrics.blocked_critical}`

*Active Users:* `{len(metrics.user_request_counts)}`"""

    # Add session statistics if provided
    if session_stats is not None:
        active = session_stats.get("active_sessions", 0)
        expired = session_stats.get("sessions_expired", 0)
        evicted = session_stats.get("sessions_evicted", 0)
        oldest_age = session_stats.get("oldest_session_age")

        message += "\n\n*Sessions:*"
        message += f"\n- Active: `{active}`"
        message += f"\n- Expired: `{expired}`"
        message += f"\n- Evicted: `{evicted}`"
        if oldest_age is not None:
            message += f"\n- Oldest: `{oldest_age:.0f}s`"

    return message
