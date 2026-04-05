"""Pytest configuration and shared fixtures for wallpanel-control."""

from __future__ import annotations

import pytest

from wallpanel_control.adapters.fake import FakeWallpanel, FakeWol
from wallpanel_control.settings import WallpanelControlSettings

from tests.fixtures.config import make_wallpanel_control_settings


@pytest.fixture
def fake_wallpanel() -> FakeWallpanel:
    """Fresh FakeWallpanel instance, reset per test."""
    return FakeWallpanel()


@pytest.fixture
def fake_wol() -> FakeWol:
    """Fresh FakeWol instance, reset per test."""
    return FakeWol()


@pytest.fixture
def wallpanel_settings() -> WallpanelControlSettings:
    """Isolated WallpanelControlSettings with test defaults."""
    return make_wallpanel_control_settings()
