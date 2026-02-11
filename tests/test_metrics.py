"""Tests for metrics and observability module."""

from __future__ import annotations

import time

import pytest

from jarvis_mk1_lite.metrics import (
    HealthStatus,
    Metrics,
    RateLimiter,
    format_metrics_message,
    get_health_status,
    metrics,
    rate_limiter,
)


class TestMetrics:
    """Tests for Metrics dataclass."""

    @pytest.fixture
    def fresh_metrics(self) -> Metrics:
        """Create a fresh metrics instance for testing."""
        return Metrics()

    def test_metrics_initialization(self, fresh_metrics: Metrics) -> None:
        """Metrics should initialize with default values."""
        assert fresh_metrics.total_requests == 0
        assert fresh_metrics.total_errors == 0
        assert fresh_metrics.total_commands == 0
        assert fresh_metrics.total_messages == 0
        assert fresh_metrics.safety_checks == 0
        assert fresh_metrics.blocked_dangerous == 0
        assert fresh_metrics.blocked_critical == 0
        assert len(fresh_metrics.latencies) == 0
        assert len(fresh_metrics.command_counts) == 0
        assert len(fresh_metrics.user_request_counts) == 0
        assert len(fresh_metrics.user_error_counts) == 0

    def test_record_request(self, fresh_metrics: Metrics) -> None:
        """Should record requests correctly."""
        fresh_metrics.record_request(123, is_command=False)

        assert fresh_metrics.total_requests == 1
        assert fresh_metrics.total_messages == 1
        assert fresh_metrics.total_commands == 0
        assert fresh_metrics.user_request_counts[123] == 1
        assert fresh_metrics.last_request_time is not None

    def test_record_command_request(self, fresh_metrics: Metrics) -> None:
        """Should record command requests correctly."""
        fresh_metrics.record_request(123, is_command=True)

        assert fresh_metrics.total_requests == 1
        assert fresh_metrics.total_messages == 0
        assert fresh_metrics.total_commands == 1

    def test_record_command(self, fresh_metrics: Metrics) -> None:
        """Should record specific commands."""
        fresh_metrics.record_command("start", 123)

        assert fresh_metrics.command_counts["start"] == 1
        assert fresh_metrics.total_commands == 1
        assert fresh_metrics.user_request_counts[123] == 1

    def test_record_multiple_commands(self, fresh_metrics: Metrics) -> None:
        """Should track multiple command types."""
        fresh_metrics.record_command("start", 123)
        fresh_metrics.record_command("help", 123)
        fresh_metrics.record_command("start", 456)

        assert fresh_metrics.command_counts["start"] == 2
        assert fresh_metrics.command_counts["help"] == 1
        assert fresh_metrics.total_commands == 3

    def test_record_error(self, fresh_metrics: Metrics) -> None:
        """Should record errors correctly."""
        fresh_metrics.record_error(123)

        assert fresh_metrics.total_errors == 1
        assert fresh_metrics.user_error_counts[123] == 1

    def test_record_latency(self, fresh_metrics: Metrics) -> None:
        """Should record latency samples."""
        fresh_metrics.record_latency(0.5)
        fresh_metrics.record_latency(1.0)

        assert len(fresh_metrics.latencies) == 2
        assert fresh_metrics.latencies[0] == 0.5
        assert fresh_metrics.latencies[1] == 1.0

    def test_record_latency_max_samples(self, fresh_metrics: Metrics) -> None:
        """Should limit latency samples to max_latency_samples."""
        fresh_metrics.max_latency_samples = 5
        for i in range(10):
            fresh_metrics.record_latency(float(i))

        assert len(fresh_metrics.latencies) == 5
        # Should keep the last 5 samples
        assert fresh_metrics.latencies == [5.0, 6.0, 7.0, 8.0, 9.0]

    def test_record_safety_check_safe(self, fresh_metrics: Metrics) -> None:
        """Should record safety checks without blocks."""
        fresh_metrics.record_safety_check()

        assert fresh_metrics.safety_checks == 1
        assert fresh_metrics.blocked_dangerous == 0
        assert fresh_metrics.blocked_critical == 0

    def test_record_safety_check_dangerous(self, fresh_metrics: Metrics) -> None:
        """Should record dangerous command blocks."""
        fresh_metrics.record_safety_check(is_dangerous=True)

        assert fresh_metrics.safety_checks == 1
        assert fresh_metrics.blocked_dangerous == 1
        assert fresh_metrics.blocked_critical == 0

    def test_record_safety_check_critical(self, fresh_metrics: Metrics) -> None:
        """Should record critical command blocks."""
        fresh_metrics.record_safety_check(is_critical=True)

        assert fresh_metrics.safety_checks == 1
        assert fresh_metrics.blocked_dangerous == 0
        assert fresh_metrics.blocked_critical == 1

    def test_get_uptime(self, fresh_metrics: Metrics) -> None:
        """Should calculate uptime correctly."""
        # Uptime should be positive
        uptime = fresh_metrics.get_uptime()
        assert uptime >= 0.0

    def test_get_average_latency_empty(self, fresh_metrics: Metrics) -> None:
        """Should return 0.0 for empty latency list."""
        assert fresh_metrics.get_average_latency() == 0.0

    def test_get_average_latency(self, fresh_metrics: Metrics) -> None:
        """Should calculate average latency correctly."""
        fresh_metrics.record_latency(1.0)
        fresh_metrics.record_latency(2.0)
        fresh_metrics.record_latency(3.0)

        assert fresh_metrics.get_average_latency() == 2.0

    def test_get_p95_latency_empty(self, fresh_metrics: Metrics) -> None:
        """Should return 0.0 for empty latency list."""
        assert fresh_metrics.get_p95_latency() == 0.0

    def test_get_p95_latency(self, fresh_metrics: Metrics) -> None:
        """Should calculate P95 latency correctly."""
        # Add 100 samples: 0.0 to 0.99
        for i in range(100):
            fresh_metrics.record_latency(float(i) / 100)

        p95 = fresh_metrics.get_p95_latency()
        # P95 should be around 0.95
        assert 0.94 <= p95 <= 0.96

    def test_get_error_rate_no_requests(self, fresh_metrics: Metrics) -> None:
        """Should return 0.0 when no requests."""
        assert fresh_metrics.get_error_rate() == 0.0

    def test_get_error_rate(self, fresh_metrics: Metrics) -> None:
        """Should calculate error rate correctly."""
        fresh_metrics.total_requests = 100
        fresh_metrics.total_errors = 10

        assert fresh_metrics.get_error_rate() == 10.0

    def test_format_uptime_seconds(self, fresh_metrics: Metrics) -> None:
        """Should format uptime with just seconds."""
        fresh_metrics.start_time = time.time() - 45

        uptime_str = fresh_metrics.format_uptime()
        assert "45s" in uptime_str

    def test_format_uptime_minutes(self, fresh_metrics: Metrics) -> None:
        """Should format uptime with minutes and seconds."""
        fresh_metrics.start_time = time.time() - (5 * 60 + 30)

        uptime_str = fresh_metrics.format_uptime()
        assert "5m" in uptime_str
        assert "30s" in uptime_str

    def test_format_uptime_hours(self, fresh_metrics: Metrics) -> None:
        """Should format uptime with hours."""
        fresh_metrics.start_time = time.time() - (2 * 3600 + 30 * 60)

        uptime_str = fresh_metrics.format_uptime()
        assert "2h" in uptime_str
        assert "30m" in uptime_str

    def test_format_uptime_days(self, fresh_metrics: Metrics) -> None:
        """Should format uptime with days."""
        fresh_metrics.start_time = time.time() - (3 * 86400)

        uptime_str = fresh_metrics.format_uptime()
        assert "3d" in uptime_str

    def test_reset(self, fresh_metrics: Metrics) -> None:
        """Should reset all metrics to initial values."""
        # Add some data
        fresh_metrics.record_request(123)
        fresh_metrics.record_error(123)
        fresh_metrics.record_command("start", 123)
        fresh_metrics.record_latency(1.0)
        fresh_metrics.record_safety_check(is_dangerous=True)

        # Reset
        fresh_metrics.reset()

        assert fresh_metrics.total_requests == 0
        assert fresh_metrics.total_errors == 0
        assert fresh_metrics.total_commands == 0
        assert fresh_metrics.total_messages == 0
        assert len(fresh_metrics.command_counts) == 0
        assert len(fresh_metrics.user_request_counts) == 0
        assert len(fresh_metrics.user_error_counts) == 0
        assert fresh_metrics.safety_checks == 0
        assert fresh_metrics.blocked_dangerous == 0
        assert fresh_metrics.blocked_critical == 0
        assert len(fresh_metrics.latencies) == 0
        assert fresh_metrics.last_request_time is None

    def test_lru_eviction_user_request_counts(self, fresh_metrics: Metrics) -> None:
        """Should evict least recently used users when over capacity."""
        fresh_metrics.max_tracked_users = 5

        # Add 7 users
        for user_id in range(1, 8):
            fresh_metrics.record_request(user_id)

        # Should only keep 5 users (the most recent: 3, 4, 5, 6, 7)
        assert len(fresh_metrics.user_request_counts) == 5
        assert 1 not in fresh_metrics.user_request_counts
        assert 2 not in fresh_metrics.user_request_counts
        assert 7 in fresh_metrics.user_request_counts

    def test_lru_eviction_user_error_counts(self, fresh_metrics: Metrics) -> None:
        """Should evict least recently used users from error counts when over capacity."""
        fresh_metrics.max_tracked_users = 5

        # Add 7 users with errors
        for user_id in range(1, 8):
            fresh_metrics.record_error(user_id)

        # Should only keep 5 users
        assert len(fresh_metrics.user_error_counts) == 5
        assert 1 not in fresh_metrics.user_error_counts
        assert 2 not in fresh_metrics.user_error_counts
        assert 7 in fresh_metrics.user_error_counts

    def test_lru_updates_position_on_access(self, fresh_metrics: Metrics) -> None:
        """Should move user to end (most recent) on access."""
        fresh_metrics.max_tracked_users = 3

        # Add users 1, 2, 3
        fresh_metrics.record_request(1)
        fresh_metrics.record_request(2)
        fresh_metrics.record_request(3)

        # Access user 1 again (should move to end)
        fresh_metrics.record_request(1)

        # Add user 4 - should evict user 2 (oldest)
        fresh_metrics.record_request(4)

        assert 2 not in fresh_metrics.user_request_counts
        assert 1 in fresh_metrics.user_request_counts
        assert 3 in fresh_metrics.user_request_counts
        assert 4 in fresh_metrics.user_request_counts


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_health_status_creation(self) -> None:
        """Should create HealthStatus correctly."""
        status = HealthStatus(
            healthy=True,
            status="healthy",
            uptime=3600.0,
            uptime_formatted="1h 0m 0s",
            total_requests=100,
            error_rate=1.5,
            avg_latency=0.5,
        )

        assert status.healthy is True
        assert status.status == "healthy"
        assert status.uptime == 3600.0
        assert status.uptime_formatted == "1h 0m 0s"
        assert status.total_requests == 100
        assert status.error_rate == 1.5
        assert status.avg_latency == 0.5
        assert status.claude_healthy is None

    def test_health_status_with_claude_healthy(self) -> None:
        """Should include Claude health status when provided."""
        status = HealthStatus(
            healthy=True,
            status="healthy",
            uptime=100.0,
            uptime_formatted="1m 40s",
            total_requests=10,
            error_rate=0.0,
            avg_latency=0.1,
            claude_healthy=True,
        )

        assert status.claude_healthy is True


class TestRateLimiter:
    """Tests for RateLimiter class."""

    @pytest.fixture
    def fresh_limiter(self) -> RateLimiter:
        """Create a fresh rate limiter for testing."""
        return RateLimiter(max_tokens=10, refill_rate=0.5)

    def test_rate_limiter_initialization(self, fresh_limiter: RateLimiter) -> None:
        """Rate limiter should initialize with correct defaults."""
        assert fresh_limiter.max_tokens == 10
        assert fresh_limiter.refill_rate == 0.5
        assert len(fresh_limiter.buckets) == 0

    def test_is_allowed_new_user(self, fresh_limiter: RateLimiter) -> None:
        """New users should have full token bucket."""
        assert fresh_limiter.is_allowed(123) is True
        # Should have consumed 1 token
        remaining = fresh_limiter.get_remaining(123)
        assert remaining < 10

    def test_is_allowed_consumes_tokens(self, fresh_limiter: RateLimiter) -> None:
        """Each allowed request should consume tokens."""
        for _ in range(10):
            assert fresh_limiter.is_allowed(123) is True

        # Should be rate limited now
        assert fresh_limiter.is_allowed(123) is False

    def test_is_allowed_custom_cost(self, fresh_limiter: RateLimiter) -> None:
        """Should support custom token costs."""
        assert fresh_limiter.is_allowed(123, cost=5.0) is True
        assert fresh_limiter.is_allowed(123, cost=5.0) is True
        # Should be rate limited now (10 tokens used)
        assert fresh_limiter.is_allowed(123, cost=1.0) is False

    def test_get_remaining(self, fresh_limiter: RateLimiter) -> None:
        """Should return correct remaining tokens."""
        # New user should have max tokens
        remaining = fresh_limiter.get_remaining(123)
        assert remaining == 10.0

        # After consuming some
        fresh_limiter.is_allowed(123)
        remaining = fresh_limiter.get_remaining(123)
        assert remaining < 10.0

    def test_get_retry_after_allowed(self, fresh_limiter: RateLimiter) -> None:
        """Should return 0 when request is allowed."""
        retry_after = fresh_limiter.get_retry_after(123)
        assert retry_after == 0.0

    def test_get_retry_after_rate_limited(self, fresh_limiter: RateLimiter) -> None:
        """Should return positive value when rate limited."""
        # Consume all tokens
        for _ in range(10):
            fresh_limiter.is_allowed(123)

        retry_after = fresh_limiter.get_retry_after(123)
        # Should need to wait for tokens to refill
        assert retry_after > 0.0

    def test_token_refill(self, fresh_limiter: RateLimiter) -> None:
        """Tokens should refill over time."""
        # Consume all tokens
        for _ in range(10):
            fresh_limiter.is_allowed(123)

        # Manually set last update time to 4 seconds ago
        tokens, _ = fresh_limiter.buckets[123]
        fresh_limiter.buckets[123] = (tokens, time.time() - 4)

        # Should have refilled (4 seconds * 0.5 rate = 2 tokens)
        remaining = fresh_limiter.get_remaining(123)
        assert remaining >= 1.5  # Allow some tolerance

    def test_reset_user(self, fresh_limiter: RateLimiter) -> None:
        """Should reset a user's bucket to full."""
        # Consume some tokens
        for _ in range(5):
            fresh_limiter.is_allowed(123)

        # Reset
        fresh_limiter.reset_user(123)

        remaining = fresh_limiter.get_remaining(123)
        assert remaining == 10.0

    def test_reset_all(self, fresh_limiter: RateLimiter) -> None:
        """Should reset all user buckets."""
        # Create buckets for multiple users
        fresh_limiter.is_allowed(123)
        fresh_limiter.is_allowed(456)

        # Reset all
        fresh_limiter.reset_all()

        assert len(fresh_limiter.buckets) == 0

    def test_separate_buckets_per_user(self, fresh_limiter: RateLimiter) -> None:
        """Each user should have separate bucket."""
        # User 123 uses tokens
        for _ in range(10):
            fresh_limiter.is_allowed(123)

        # User 456 should still have tokens
        assert fresh_limiter.is_allowed(456) is True


class TestGetHealthStatus:
    """Tests for get_health_status function."""

    @pytest.fixture(autouse=True)
    def reset_global_metrics(self) -> None:
        """Reset global metrics before each test."""
        metrics.reset()

    def test_get_health_status_healthy(self) -> None:
        """Should return healthy status when error rate is low."""
        metrics.total_requests = 100
        metrics.total_errors = 5  # 5% error rate

        status = get_health_status()

        assert status.healthy is True
        assert status.status == "healthy"

    def test_get_health_status_degraded(self) -> None:
        """Should return degraded status when error rate is high."""
        metrics.total_requests = 100
        metrics.total_errors = 15  # 15% error rate

        status = get_health_status()

        assert status.healthy is False
        assert status.status == "degraded"

    def test_get_health_status_includes_metrics(self) -> None:
        """Should include metrics in health status."""
        metrics.total_requests = 50
        metrics.record_latency(0.5)
        metrics.record_latency(1.0)

        status = get_health_status()

        assert status.total_requests == 50
        assert status.avg_latency == 0.75

    def test_get_health_status_with_claude(self) -> None:
        """Should include Claude health when provided."""
        status = get_health_status(claude_healthy=True)

        assert status.claude_healthy is True


class TestFormatMetricsMessage:
    """Tests for format_metrics_message function."""

    @pytest.fixture(autouse=True)
    def reset_global_metrics(self) -> None:
        """Reset global metrics before each test."""
        metrics.reset()

    def test_format_metrics_message_basic(self) -> None:
        """Should format basic metrics message."""
        message = format_metrics_message()

        assert "*Application Metrics*" in message
        assert "*Status:*" in message
        assert "*Uptime:*" in message
        assert "*Requests:*" in message
        assert "*Latency:*" in message
        assert "*Safety:*" in message
        assert "*Active Users:*" in message

    def test_format_metrics_message_with_data(self) -> None:
        """Should include actual metrics data."""
        metrics.total_requests = 100
        metrics.total_commands = 25
        metrics.total_messages = 75
        metrics.total_errors = 5
        metrics.safety_checks = 50
        metrics.blocked_dangerous = 3
        metrics.blocked_critical = 1

        message = format_metrics_message()

        assert "100" in message  # total requests
        assert "25" in message  # commands
        assert "75" in message  # messages
        assert "5" in message  # errors

    def test_format_metrics_message_with_session_stats(self) -> None:
        """Should include session statistics when provided."""
        session_stats: dict[str, int | float | None] = {
            "active_sessions": 42,
            "sessions_expired": 10,
            "sessions_evicted": 5,
            "oldest_session_age": 3600.5,
        }

        message = format_metrics_message(session_stats)

        assert "*Sessions:*" in message
        assert "Active: `42`" in message
        assert "Expired: `10`" in message
        assert "Evicted: `5`" in message
        assert "Oldest: `3600s`" in message  # should be formatted as integer seconds

    def test_format_metrics_message_with_session_stats_no_oldest(self) -> None:
        """Should handle session stats with None oldest_session_age."""
        session_stats: dict[str, int | float | None] = {
            "active_sessions": 0,
            "sessions_expired": 0,
            "sessions_evicted": 0,
            "oldest_session_age": None,
        }

        message = format_metrics_message(session_stats)

        assert "*Sessions:*" in message
        assert "Active: `0`" in message
        assert "Oldest:" not in message  # should not show when None

    def test_format_metrics_message_without_session_stats(self) -> None:
        """Should not include session section when stats not provided."""
        message = format_metrics_message()

        assert "*Sessions:*" not in message


class TestGlobalInstances:
    """Tests for global metrics and rate_limiter instances."""

    def test_global_metrics_exists(self) -> None:
        """Global metrics instance should exist."""
        assert metrics is not None
        assert isinstance(metrics, Metrics)

    def test_global_rate_limiter_exists(self) -> None:
        """Global rate limiter instance should exist."""
        assert rate_limiter is not None
        assert isinstance(rate_limiter, RateLimiter)

    def test_global_metrics_is_singleton(self) -> None:
        """Global metrics should be the same instance."""
        from jarvis_mk1_lite.metrics import metrics as metrics2

        assert metrics is metrics2

    def test_global_rate_limiter_is_singleton(self) -> None:
        """Global rate limiter should be the same instance."""
        from jarvis_mk1_lite.metrics import rate_limiter as limiter2

        assert rate_limiter is limiter2
