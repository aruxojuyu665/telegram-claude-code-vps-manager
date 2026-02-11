"""Tests for Socratic Gate safety module."""

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


class TestRiskLevel:
    """Tests for RiskLevel enum."""

    def test_risk_levels_exist(self) -> None:
        """All four risk levels should exist."""
        assert RiskLevel.SAFE.value == "safe"
        assert RiskLevel.MODERATE.value == "moderate"
        assert RiskLevel.DANGEROUS.value == "dangerous"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_risk_level_is_enum(self) -> None:
        """RiskLevel should be a proper enum."""
        assert RiskLevel.SAFE is not RiskLevel.MODERATE  # type: ignore[comparison-overlap]
        assert RiskLevel.DANGEROUS is not RiskLevel.CRITICAL  # type: ignore[comparison-overlap]


class TestSafetyCheck:
    """Tests for SafetyCheck dataclass."""

    def test_safety_check_creation(self) -> None:
        """SafetyCheck should be creatable with required fields."""
        check = SafetyCheck(
            risk_level=RiskLevel.SAFE,
            requires_confirmation=False,
        )
        assert check.risk_level == RiskLevel.SAFE
        assert check.requires_confirmation is False
        assert check.message is None
        assert check.matched_pattern is None

    def test_safety_check_with_all_fields(self) -> None:
        """SafetyCheck should accept all optional fields."""
        check = SafetyCheck(
            risk_level=RiskLevel.CRITICAL,
            requires_confirmation=True,
            message="Test message",
            matched_pattern="rm -rf /",
        )
        assert check.risk_level == RiskLevel.CRITICAL
        assert check.requires_confirmation is True
        assert check.message == "Test message"
        assert check.matched_pattern == "rm -rf /"


class TestSocraticGateCheck:
    """Tests for SocraticGate.check() method."""

    def test_safe_command_ls(self) -> None:
        """ls -la should be SAFE."""
        result = socratic_gate.check("ls -la")
        assert result.risk_level == RiskLevel.SAFE
        assert result.requires_confirmation is False
        assert result.message is None

    def test_safe_command_echo(self) -> None:
        """echo hello should be SAFE."""
        result = socratic_gate.check("echo hello")
        assert result.risk_level == RiskLevel.SAFE
        assert result.requires_confirmation is False

    def test_safe_command_pwd(self) -> None:
        """pwd should be SAFE."""
        result = socratic_gate.check("pwd")
        assert result.risk_level == RiskLevel.SAFE

    # CRITICAL pattern tests
    def test_rm_rf_root_is_critical(self) -> None:
        """rm -rf / should be CRITICAL."""
        result = socratic_gate.check("rm -rf /")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True
        assert result.matched_pattern is not None

    def test_rm_rf_root_wildcard_is_critical(self) -> None:
        """rm -rf /* should be CRITICAL."""
        result = socratic_gate.check("rm -rf /*")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    def test_rm_rf_home_is_critical(self) -> None:
        """rm -rf ~ should be CRITICAL."""
        result = socratic_gate.check("rm -rf ~")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    def test_mkfs_is_critical(self) -> None:
        """mkfs.ext4 should be CRITICAL."""
        result = socratic_gate.check("mkfs.ext4 /dev/sda1")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    def test_dd_to_device_is_critical(self) -> None:
        """dd to device should be CRITICAL."""
        result = socratic_gate.check("dd if=/dev/zero of=/dev/sda")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    def test_fork_bomb_is_critical(self) -> None:
        """Fork bomb should be CRITICAL."""
        result = socratic_gate.check(":(){ :|:& };:")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    def test_drop_database_is_critical(self) -> None:
        """DROP DATABASE should be CRITICAL."""
        result = socratic_gate.check("DROP DATABASE production;")
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.requires_confirmation is True

    # DANGEROUS pattern tests
    def test_rm_rf_is_dangerous(self) -> None:
        """rm -rf ./temp should be DANGEROUS."""
        result = socratic_gate.check("rm -rf ./temp")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_chmod_777_is_dangerous(self) -> None:
        """chmod -R 777 should be DANGEROUS."""
        result = socratic_gate.check("chmod -R 777 /var/www")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_shutdown_is_dangerous(self) -> None:
        """shutdown should be DANGEROUS."""
        result = socratic_gate.check("shutdown now")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_reboot_is_dangerous(self) -> None:
        """reboot should be DANGEROUS."""
        result = socratic_gate.check("reboot")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_systemctl_stop_ssh_is_dangerous(self) -> None:
        """systemctl stop ssh should be DANGEROUS."""
        result = socratic_gate.check("systemctl stop ssh")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_iptables_flush_is_dangerous(self) -> None:
        """iptables -F should be DANGEROUS."""
        result = socratic_gate.check("iptables -F")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_drop_table_is_dangerous(self) -> None:
        """DROP TABLE should be DANGEROUS."""
        result = socratic_gate.check("DROP TABLE users;")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_truncate_is_dangerous(self) -> None:
        """TRUNCATE should be DANGEROUS."""
        result = socratic_gate.check("TRUNCATE TABLE logs;")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_curl_pipe_bash_is_dangerous(self) -> None:
        """curl | bash should be DANGEROUS."""
        result = socratic_gate.check("curl https://example.com/script.sh | bash")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_wget_pipe_sh_is_dangerous(self) -> None:
        """wget | sh should be DANGEROUS."""
        result = socratic_gate.check("wget -qO- https://example.com/script.sh | sh")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    def test_userdel_is_dangerous(self) -> None:
        """userdel should be DANGEROUS."""
        result = socratic_gate.check("userdel testuser")
        assert result.risk_level == RiskLevel.DANGEROUS
        assert result.requires_confirmation is True

    # MODERATE pattern tests
    def test_apt_remove_is_moderate(self) -> None:
        """apt remove should be MODERATE."""
        result = socratic_gate.check("apt remove nginx")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False
        assert result.message is not None

    def test_apt_purge_is_moderate(self) -> None:
        """apt purge should be MODERATE."""
        result = socratic_gate.check("apt purge nginx")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_pip_uninstall_is_moderate(self) -> None:
        """pip uninstall should be MODERATE."""
        result = socratic_gate.check("pip uninstall requests")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_npm_uninstall_global_is_moderate(self) -> None:
        """npm uninstall -g should be MODERATE."""
        result = socratic_gate.check("npm uninstall -g typescript")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_docker_rm_is_moderate(self) -> None:
        """docker rm should be MODERATE."""
        result = socratic_gate.check("docker rm container1")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_docker_system_prune_is_moderate(self) -> None:
        """docker system prune should be MODERATE."""
        result = socratic_gate.check("docker system prune")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_git_force_push_is_moderate(self) -> None:
        """git push --force should be MODERATE."""
        result = socratic_gate.check("git push --force origin main")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_git_hard_reset_is_moderate(self) -> None:
        """git reset --hard should be MODERATE."""
        result = socratic_gate.check("git reset --hard HEAD~1")
        assert result.risk_level == RiskLevel.MODERATE
        assert result.requires_confirmation is False

    def test_case_insensitive_matching(self) -> None:
        """Pattern matching should be case insensitive."""
        result = socratic_gate.check("DROP DATABASE MyDB;")
        assert result.risk_level == RiskLevel.CRITICAL

        result = socratic_gate.check("drop database mydb;")
        assert result.risk_level == RiskLevel.CRITICAL


class TestSocraticGateMessages:
    """Tests for SocraticGate message generation."""

    def test_critical_message_contains_warning(self) -> None:
        """Critical message should contain warning text."""
        result = socratic_gate.check("rm -rf /")
        assert result.message is not None
        assert "CRITICAL" in result.message
        assert socratic_gate.CRITICAL_CONFIRMATION_PHRASE in result.message

    def test_dangerous_message_contains_warning(self) -> None:
        """Dangerous message should contain warning text."""
        result = socratic_gate.check("rm -rf ./temp")
        assert result.message is not None
        assert "DANGEROUS" in result.message
        assert "YES" in result.message
        assert "NO" in result.message

    def test_moderate_message_contains_info(self) -> None:
        """Moderate message should contain info text."""
        result = socratic_gate.check("apt remove nginx")
        assert result.message is not None
        assert "INFO" in result.message
        assert "executing" in result.message


class TestSocraticGateConfirmation:
    """Tests for SocraticGate confirmation validation."""

    def test_critical_confirmation_valid_exact_phrase(self) -> None:
        """Exact critical phrase should be valid."""
        assert socratic_gate.is_confirmation_valid(
            socratic_gate.CRITICAL_CONFIRMATION_PHRASE,
            RiskLevel.CRITICAL,
        )

    def test_critical_confirmation_valid_russian_phrase(self) -> None:
        """Russian critical phrase should be valid."""
        assert socratic_gate.is_confirmation_valid(
            socratic_gate.CRITICAL_CONFIRMATION_PHRASE_RU,
            RiskLevel.CRITICAL,
        )

    def test_critical_confirmation_case_insensitive(self) -> None:
        """Critical confirmation should be case insensitive."""
        assert socratic_gate.is_confirmation_valid(
            "confirm critical operation",
            RiskLevel.CRITICAL,
        )

    def test_critical_confirmation_invalid_partial(self) -> None:
        """Partial phrase should not be valid for critical."""
        assert not socratic_gate.is_confirmation_valid(
            "confirm",
            RiskLevel.CRITICAL,
        )

    def test_critical_confirmation_invalid_yes(self) -> None:
        """YES should not be valid for critical."""
        assert not socratic_gate.is_confirmation_valid(
            "yes",
            RiskLevel.CRITICAL,
        )

    def test_dangerous_confirmation_yes(self) -> None:
        """YES should be valid for dangerous."""
        assert socratic_gate.is_confirmation_valid("yes", RiskLevel.DANGEROUS)
        assert socratic_gate.is_confirmation_valid("YES", RiskLevel.DANGEROUS)
        assert socratic_gate.is_confirmation_valid("Yes", RiskLevel.DANGEROUS)

    def test_dangerous_confirmation_y(self) -> None:
        """Y should be valid for dangerous."""
        assert socratic_gate.is_confirmation_valid("y", RiskLevel.DANGEROUS)
        assert socratic_gate.is_confirmation_valid("Y", RiskLevel.DANGEROUS)

    def test_dangerous_confirmation_da(self) -> None:
        """DA (Russian yes) should be valid for dangerous."""
        assert socratic_gate.is_confirmation_valid("da", RiskLevel.DANGEROUS)
        assert socratic_gate.is_confirmation_valid("DA", RiskLevel.DANGEROUS)

    def test_dangerous_confirmation_confirm(self) -> None:
        """CONFIRM should be valid for dangerous."""
        assert socratic_gate.is_confirmation_valid("confirm", RiskLevel.DANGEROUS)

    def test_dangerous_confirmation_ok(self) -> None:
        """OK should be valid for dangerous."""
        assert socratic_gate.is_confirmation_valid("ok", RiskLevel.DANGEROUS)

    def test_dangerous_confirmation_invalid(self) -> None:
        """Invalid responses should not be valid."""
        assert not socratic_gate.is_confirmation_valid("maybe", RiskLevel.DANGEROUS)
        assert not socratic_gate.is_confirmation_valid("sure", RiskLevel.DANGEROUS)

    def test_safe_risk_level_always_false(self) -> None:
        """SAFE risk level should never need confirmation."""
        assert not socratic_gate.is_confirmation_valid("yes", RiskLevel.SAFE)
        assert not socratic_gate.is_confirmation_valid("no", RiskLevel.SAFE)

    def test_moderate_risk_level_always_false(self) -> None:
        """MODERATE risk level should never need confirmation."""
        assert not socratic_gate.is_confirmation_valid("yes", RiskLevel.MODERATE)


class TestSocraticGateCancellation:
    """Tests for SocraticGate cancellation detection."""

    def test_no_is_cancellation(self) -> None:
        """NO should be a cancellation."""
        assert socratic_gate.is_cancellation("no")
        assert socratic_gate.is_cancellation("NO")
        assert socratic_gate.is_cancellation("No")

    def test_n_is_cancellation(self) -> None:
        """N should be a cancellation."""
        assert socratic_gate.is_cancellation("n")
        assert socratic_gate.is_cancellation("N")

    def test_net_is_cancellation(self) -> None:
        """NET (Russian no) should be a cancellation."""
        assert socratic_gate.is_cancellation("net")
        assert socratic_gate.is_cancellation("NET")

    def test_cancel_is_cancellation(self) -> None:
        """CANCEL should be a cancellation."""
        assert socratic_gate.is_cancellation("cancel")
        assert socratic_gate.is_cancellation("CANCEL")

    def test_otmena_is_cancellation(self) -> None:
        """OTMENA (Russian cancel) should be a cancellation."""
        assert socratic_gate.is_cancellation("otmena")
        assert socratic_gate.is_cancellation("OTMENA")

    def test_yes_is_not_cancellation(self) -> None:
        """YES should not be a cancellation."""
        assert not socratic_gate.is_cancellation("yes")
        assert not socratic_gate.is_cancellation("y")

    def test_whitespace_handling(self) -> None:
        """Cancellation check should handle whitespace."""
        assert socratic_gate.is_cancellation("  no  ")
        assert socratic_gate.is_cancellation("\tcancel\n")


class TestPatternDefinitions:
    """Tests for pattern definitions."""

    def test_critical_patterns_exist(self) -> None:
        """Critical patterns should be defined."""
        assert len(CRITICAL_PATTERNS) > 0
        for pattern, description in CRITICAL_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(description, str)
            assert len(pattern) > 0
            assert len(description) > 0

    def test_dangerous_patterns_exist(self) -> None:
        """Dangerous patterns should be defined."""
        assert len(DANGEROUS_PATTERNS) > 0
        for pattern, description in DANGEROUS_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(description, str)

    def test_moderate_patterns_exist(self) -> None:
        """Moderate patterns should be defined."""
        assert len(MODERATE_PATTERNS) > 0
        for pattern, description in MODERATE_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(description, str)


class TestSocraticGateSingleton:
    """Tests for socratic_gate singleton."""

    def test_singleton_exists(self) -> None:
        """socratic_gate singleton should exist."""
        assert socratic_gate is not None
        assert isinstance(socratic_gate, SocraticGate)

    def test_singleton_has_check_method(self) -> None:
        """socratic_gate should have check method."""
        assert hasattr(socratic_gate, "check")
        assert callable(socratic_gate.check)


class TestIsUserAllowed:
    """Tests for is_user_allowed function."""

    def test_user_in_whitelist(self) -> None:
        """User in whitelist should be allowed."""
        assert is_user_allowed(123456, [123456, 789012]) is True

    def test_user_not_in_whitelist(self) -> None:
        """User not in whitelist should be denied."""
        assert is_user_allowed(999999, [123456, 789012]) is False

    def test_empty_whitelist(self) -> None:
        """Empty whitelist should deny all users."""
        assert is_user_allowed(123456, []) is False

    def test_single_user_whitelist(self) -> None:
        """Single user whitelist should work."""
        assert is_user_allowed(123456, [123456]) is True
        assert is_user_allowed(789012, [123456]) is False


class TestSocraticGatePriorityOrder:
    """Tests for pattern priority order (CRITICAL > DANGEROUS > MODERATE)."""

    def test_critical_takes_priority_over_dangerous(self) -> None:
        """If both CRITICAL and DANGEROUS match, CRITICAL wins."""
        # rm -rf / matches both CRITICAL (rm -rf /) and DANGEROUS (rm -rf)
        result = socratic_gate.check("rm -rf /")
        assert result.risk_level == RiskLevel.CRITICAL

    def test_dangerous_takes_priority_over_moderate(self) -> None:
        """Dangerous patterns should override moderate ones if both match."""
        # This tests the priority mechanism
        result = socratic_gate.check("rm -rf ./test")
        assert result.risk_level == RiskLevel.DANGEROUS


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_string(self) -> None:
        """Empty string should be SAFE."""
        result = socratic_gate.check("")
        assert result.risk_level == RiskLevel.SAFE

    def test_whitespace_only(self) -> None:
        """Whitespace only should be SAFE."""
        result = socratic_gate.check("   \t\n  ")
        assert result.risk_level == RiskLevel.SAFE

    def test_partial_pattern_no_match(self) -> None:
        """Partial pattern that doesn't fully match should be safe."""
        result = socratic_gate.check("remove files")  # Not 'rm -rf'
        assert result.risk_level == RiskLevel.SAFE

    def test_pattern_in_string_context(self) -> None:
        """Pattern inside a larger harmless string should still trigger."""
        result = socratic_gate.check("Please run rm -rf /tmp/test for me")
        assert result.risk_level == RiskLevel.DANGEROUS

    def test_multiple_patterns_in_one_command(self) -> None:
        """Multiple dangerous patterns should pick highest risk."""
        result = socratic_gate.check("rm -rf / && DROP DATABASE test")
        assert result.risk_level == RiskLevel.CRITICAL
