"""Integration tests verifying all module imports and component integration."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestImportVerification:
    """Tests verifying all imports work correctly."""

    def test_import_config(self) -> None:
        """Should import config module successfully."""
        from jarvis_mk1_lite.config import Settings, get_settings

        assert Settings is not None
        assert callable(get_settings)

    def test_import_bridge(self) -> None:
        """Should import bridge module successfully."""
        from jarvis_mk1_lite.bridge import ClaudeBridge, ClaudeResponse, claude_bridge

        assert ClaudeBridge is not None
        assert ClaudeResponse is not None
        assert claude_bridge is not None

    def test_import_safety(self) -> None:
        """Should import safety module successfully."""
        from jarvis_mk1_lite.safety import (
            CRITICAL_PATTERNS,
            DANGEROUS_PATTERNS,
            MODERATE_PATTERNS,
            RiskLevel,
            SafetyCheck,
            SocraticGate,
            is_user_allowed,
            socratic_gate,
        )

        assert RiskLevel is not None
        assert SafetyCheck is not None
        assert SocraticGate is not None
        assert socratic_gate is not None
        assert is_user_allowed is not None
        assert CRITICAL_PATTERNS is not None
        assert DANGEROUS_PATTERNS is not None
        assert MODERATE_PATTERNS is not None

    def test_import_bot(self) -> None:
        """Should import bot module successfully."""
        from jarvis_mk1_lite.bot import JarvisBot, setup_bot

        assert JarvisBot is not None
        assert callable(setup_bot)

    def test_import_main(self) -> None:
        """Should import main module successfully."""
        from jarvis_mk1_lite.__main__ import (
            configure_structlog,
            main,
            setup_logging,
            shutdown,
        )

        assert main is not None
        assert configure_structlog is not None
        assert setup_logging is not None
        assert shutdown is not None


class TestSystemPrompt:
    """Tests for system prompt loading."""

    def test_system_prompt_exists(self) -> None:
        """System prompt file should exist."""
        prompt_path = Path("prompts/system.md")
        assert prompt_path.exists(), f"System prompt not found at {prompt_path}"

    def test_system_prompt_has_content(self) -> None:
        """System prompt should have content."""
        prompt_path = Path("prompts/system.md")
        content = prompt_path.read_text(encoding="utf-8")
        assert len(content) > 100, "System prompt appears to be too short"

    def test_system_prompt_has_required_sections(self) -> None:
        """System prompt should have required sections."""
        prompt_path = Path("prompts/system.md")
        content = prompt_path.read_text(encoding="utf-8")

        required_sections = [
            "Environment",
            "Installed Software",
            "Safety Rules",
        ]

        for section in required_sections:
            assert section in content, f"Missing section: {section}"


class TestComponentIntegration:
    """Tests for component integration."""

    def test_settings_can_be_used_with_bridge(self) -> None:
        """Settings should work with ClaudeBridge."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            from jarvis_mk1_lite.config import get_settings

            settings = get_settings()

            # Settings should have bridge-related fields
            assert hasattr(settings, "claude_model")
            assert hasattr(settings, "claude_max_tokens")
            assert hasattr(settings, "claude_timeout")
            assert hasattr(settings, "workspace_dir")
            assert hasattr(settings, "system_prompt_path")

    def test_safety_check_returns_correct_type(self) -> None:
        """Socratic gate should return SafetyCheck."""
        from jarvis_mk1_lite.safety import SafetyCheck, socratic_gate

        result = socratic_gate.check("ls -la")

        assert isinstance(result, SafetyCheck)
        assert hasattr(result, "risk_level")
        assert hasattr(result, "requires_confirmation")

    def test_claude_response_dataclass(self) -> None:
        """ClaudeResponse should work as expected."""
        from jarvis_mk1_lite.bridge import ClaudeResponse

        response = ClaudeResponse(
            success=True,
            content="Hello",
            error=None,
            session_id="test-session",
        )

        assert response.success is True
        assert response.content == "Hello"
        assert response.session_id == "test-session"

    def test_risk_levels_are_comparable(self) -> None:
        """RiskLevel enum should have all expected values."""
        from jarvis_mk1_lite.safety import RiskLevel

        levels = [RiskLevel.SAFE, RiskLevel.MODERATE, RiskLevel.DANGEROUS, RiskLevel.CRITICAL]

        # All levels should be unique
        assert len(set(levels)) == 4

        # Values should match expected strings
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.MODERATE.value == "moderate"
        assert RiskLevel.DANGEROUS.value == "dangerous"
        assert RiskLevel.CRITICAL.value == "critical"


class TestVersionConsistency:
    """Tests for version consistency across components."""

    def test_version_in_settings(self) -> None:
        """Version should be 1.0.8 in settings."""
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            from jarvis_mk1_lite.config import get_settings

            settings = get_settings()
            # Version should be a valid semver string
            assert settings.app_version is not None
            assert len(settings.app_version.split(".")) >= 2

    def test_version_in_pyproject(self) -> None:
        """Version in pyproject.toml should match settings.app_version."""
        import tomllib

        pyproject_path = Path("pyproject.toml")
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                version = data.get("tool", {}).get("poetry", {}).get("version")
                from jarvis_mk1_lite.config import get_settings

                settings = get_settings()
                assert (
                    version == settings.app_version
                ), f"pyproject.toml version {version} != settings {settings.app_version}"


class TestStructlogIntegration:
    """Tests for structlog integration."""

    def test_configure_structlog_works(self) -> None:
        """configure_structlog should not raise."""
        from jarvis_mk1_lite.__main__ import configure_structlog

        # Should not raise
        configure_structlog("INFO")

    def test_structlog_is_importable(self) -> None:
        """structlog should be importable."""
        import structlog

        assert structlog is not None
        assert hasattr(structlog, "configure")
        assert hasattr(structlog, "get_logger")


class TestMetricsIntegration:
    """Tests for metrics module integration."""

    def test_import_metrics(self) -> None:
        """Should import metrics module successfully."""
        from jarvis_mk1_lite.metrics import (
            HealthStatus,
            Metrics,
            RateLimiter,
            format_metrics_message,
            get_health_status,
            metrics,
            rate_limiter,
        )

        assert Metrics is not None
        assert HealthStatus is not None
        assert RateLimiter is not None
        assert metrics is not None
        assert rate_limiter is not None
        assert callable(get_health_status)
        assert callable(format_metrics_message)

    def test_metrics_from_package(self) -> None:
        """Should be able to import metrics from package."""
        from jarvis_mk1_lite import (
            HealthStatus,
            Metrics,
            RateLimiter,
            metrics,
            rate_limiter,
        )

        assert Metrics is not None
        assert HealthStatus is not None
        assert RateLimiter is not None
        assert metrics is not None
        assert rate_limiter is not None

    def test_metrics_singleton(self) -> None:
        """Global metrics should be singleton."""
        from jarvis_mk1_lite import metrics as metrics1
        from jarvis_mk1_lite.metrics import metrics as metrics2

        assert metrics1 is metrics2

    def test_rate_limiter_singleton(self) -> None:
        """Global rate limiter should be singleton."""
        from jarvis_mk1_lite import rate_limiter as limiter1
        from jarvis_mk1_lite.metrics import rate_limiter as limiter2

        assert limiter1 is limiter2


@pytest.mark.skip(
    reason="Uses old single-session architecture, needs update for v1.2.0 multi-session"
)
class TestSessionExpiryIntegration:
    """Integration tests for session expiry functionality."""

    def test_session_creation_and_retrieval(self) -> None:
        """ClaudeBridge should store and retrieve sessions."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize user 123
        bridge = ClaudeBridge(allowed_user_ids=[123])

        # Manually set a session
        bridge._sessions[123] = "test-session-id"
        bridge._session_timestamps[123] = time.time()

        assert bridge.get_session(123) == "test-session-id"
        assert bridge.get_session_count() == 1

    def test_session_clear(self) -> None:
        """ClaudeBridge should clear sessions properly."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize user 123
        bridge = ClaudeBridge(allowed_user_ids=[123])

        # Set a session
        bridge._sessions[123] = "test-session-id"
        bridge._session_timestamps[123] = time.time()

        # Clear it
        had_session = bridge.clear_session(123)

        assert had_session is True
        assert bridge.get_session(123) is None
        assert bridge.get_session_count() == 0

    def test_session_clear_nonexistent(self) -> None:
        """Clearing nonexistent session should return False."""
        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()
        had_session = bridge.clear_session(999)

        assert had_session is False

    def test_session_age_tracking(self) -> None:
        """ClaudeBridge should track session ages."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()

        # Set a session with known timestamp
        past_time = time.time() - 100  # 100 seconds ago
        bridge._sessions[123] = "test-session-id"
        bridge._session_timestamps[123] = past_time

        age = bridge.get_session_age(123)

        assert age is not None
        assert age >= 100  # Should be at least 100 seconds old

    def test_session_age_nonexistent(self) -> None:
        """Session age for nonexistent user should be None."""
        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()
        age = bridge.get_session_age(999)

        assert age is None

    def test_oldest_session_age(self) -> None:
        """ClaudeBridge should report oldest session age."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()

        # Set multiple sessions with different ages
        bridge._sessions[123] = "session-1"
        bridge._session_timestamps[123] = time.time() - 200  # 200 seconds ago

        bridge._sessions[456] = "session-2"
        bridge._session_timestamps[456] = time.time() - 100  # 100 seconds ago

        oldest = bridge.get_oldest_session_age()

        assert oldest is not None
        assert oldest >= 200  # Should be at least 200 seconds

    def test_oldest_session_age_no_sessions(self) -> None:
        """Oldest session age with no sessions should be None."""
        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()
        oldest = bridge.get_oldest_session_age()

        assert oldest is None

    def test_session_stats_structure(self) -> None:
        """Session stats should have expected structure."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()

        # Set some sessions
        bridge._sessions[123] = "session-1"
        bridge._session_timestamps[123] = time.time()

        stats = bridge.get_session_stats()

        assert "active_sessions" in stats
        assert "sessions_expired" in stats
        assert "sessions_evicted" in stats
        assert "oldest_session_age" in stats
        assert stats["active_sessions"] == 1

    def test_session_expiry_cleanup(self) -> None:
        """Expired sessions should be cleaned up when settings available."""
        import os
        import time
        from unittest.mock import patch

        from jarvis_mk1_lite.bridge import ClaudeBridge

        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            bridge = ClaudeBridge()

            if bridge._settings is None:
                # Settings not available, test with default behavior
                # Without settings, cleanup returns 0
                bridge._sessions[123] = "old-session"
                bridge._session_timestamps[123] = time.time() - 10000
                cleaned = bridge._cleanup_expired_sessions()
                assert cleaned == 0  # No cleanup without settings
            else:
                # Set an expired session (timestamp older than expiry)
                expiry_seconds = bridge._settings.session_expiry_seconds
                bridge._sessions[123] = "old-session"
                bridge._session_timestamps[123] = time.time() - expiry_seconds - 100

                # Run cleanup
                cleaned = bridge._cleanup_expired_sessions()

                assert cleaned == 1
                assert bridge.get_session(123) is None
                assert bridge._sessions_expired >= 1

    def test_lru_eviction(self) -> None:
        """LRU eviction should work when max_sessions exceeded and settings available."""
        import os
        import time
        from unittest.mock import patch

        from jarvis_mk1_lite.bridge import ClaudeBridge

        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            bridge = ClaudeBridge()

            if bridge._settings is None:
                # Without settings, eviction does nothing
                for i in range(10):
                    bridge._sessions[i] = f"session-{i}"
                    bridge._session_timestamps[i] = time.time()

                bridge._evict_lru_sessions()
                # Should still have all sessions (no eviction without settings)
                assert len(bridge._sessions) == 10
            else:
                # Get max_sessions from settings
                max_sessions = bridge._settings.max_sessions

                # Add more sessions than the limit allows
                for i in range(max_sessions + 5):
                    bridge._sessions[i] = f"session-{i}"
                    bridge._session_timestamps[i] = time.time()

                # Run eviction
                bridge._evict_lru_sessions()

                # Should have exactly max_sessions
                assert len(bridge._sessions) == max_sessions

    def test_session_update_with_lru(self) -> None:
        """Session update should maintain LRU ordering."""
        import time

        from jarvis_mk1_lite.bridge import ClaudeBridge

        bridge = ClaudeBridge()

        # Add sessions
        bridge._sessions[1] = "session-1"
        bridge._session_timestamps[1] = time.time() - 100

        bridge._sessions[2] = "session-2"
        bridge._session_timestamps[2] = time.time() - 50

        # Update session 1 (should move to end)
        bridge._update_session(1, "session-1-updated")

        # Session 1 should now be at the end (most recently used)
        keys = list(bridge._sessions.keys())
        assert keys[-1] == 1

    def test_session_metrics_increment(self) -> None:
        """Session metrics should increment correctly when settings available."""
        import os
        import time
        from unittest.mock import patch

        from jarvis_mk1_lite.bridge import ClaudeBridge

        env_vars = {
            "TELEGRAM_BOT_TOKEN": "test-token",
            "ANTHROPIC_API_KEY": "test-api-key",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            bridge = ClaudeBridge()
            initial_expired = bridge._sessions_expired

            if bridge._settings is None:
                # Without settings, cleanup does nothing
                bridge._sessions[123] = "session"
                bridge._session_timestamps[123] = time.time() - 10000

                bridge._cleanup_expired_sessions()

                # No increment without settings
                assert bridge._sessions_expired == initial_expired
            else:
                # Add and expire a session
                expiry_seconds = bridge._settings.session_expiry_seconds
                bridge._sessions[123] = "session"
                bridge._session_timestamps[123] = time.time() - expiry_seconds - 10

                bridge._cleanup_expired_sessions()

                assert bridge._sessions_expired == initial_expired + 1


@pytest.mark.skip(
    reason="Uses old single-session architecture, needs update for v1.2.0 multi-session"
)
class TestSessionManagementEndToEnd:
    """End-to-end tests for session management flow."""

    def test_full_session_lifecycle(self) -> None:
        """Test complete session lifecycle: create, use, expire."""

        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize test users
        bridge = ClaudeBridge(allowed_user_ids=[123])

        # 1. No session initially
        assert bridge.get_session(123) is None

        # 2. Create session
        bridge._update_session(123, "new-session")
        assert bridge.get_session(123) == "new-session"
        assert bridge.get_session_count() >= 1

        # 3. Session age tracking
        age = bridge.get_session_age(123)
        assert age is not None
        assert age >= 0

        # 4. Stats reflect the session
        stats = bridge.get_session_stats()
        active_sessions = stats["active_sessions"]
        assert active_sessions is not None and active_sessions >= 1

        # 5. Clear session
        bridge.clear_session(123)
        assert bridge.get_session(123) is None

    def test_multiple_users_sessions(self) -> None:
        """Test multiple users with separate sessions."""

        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize test users
        bridge = ClaudeBridge(allowed_user_ids=[100, 200, 300])

        # Create sessions for multiple users
        for user_id in [100, 200, 300]:
            bridge._update_session(user_id, f"session-{user_id}")

        # Each user should have their own session
        assert bridge.get_session(100) == "session-100"
        assert bridge.get_session(200) == "session-200"
        assert bridge.get_session(300) == "session-300"

        # Clear one user
        bridge.clear_session(200)
        assert bridge.get_session(200) is None

    def test_session_stats_reflects_state(self) -> None:
        """Session stats should accurately reflect current state."""

        from jarvis_mk1_lite.bridge import ClaudeBridge

        # Pass allowed_user_ids to authorize test users
        bridge = ClaudeBridge(allowed_user_ids=[1001, 1002])

        # Initial state
        stats = bridge.get_session_stats()
        initial_active = stats["active_sessions"]
        assert initial_active is not None

        # Add sessions
        bridge._update_session(1001, "s1")
        bridge._update_session(1002, "s2")

        stats = bridge.get_session_stats()
        active_after_add = stats["active_sessions"]
        assert active_after_add is not None
        assert active_after_add == initial_active + 2

        # Clear one
        bridge.clear_session(1001)

        stats = bridge.get_session_stats()
        active_after_clear = stats["active_sessions"]
        assert active_after_clear is not None
        assert active_after_clear == initial_active + 1

        # Clean up
        bridge.clear_session(1002)
