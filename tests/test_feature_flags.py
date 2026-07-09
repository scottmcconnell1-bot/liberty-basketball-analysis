"""Tests for feature flags outside Flask request context."""


def test_feature_enabled_without_app_context():
    from helpers import feature_enabled

    assert feature_enabled("ENABLE_AUTO_STATS_M1") is True
