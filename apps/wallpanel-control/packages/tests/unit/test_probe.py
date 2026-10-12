"""Unit tests for the probe's action revision tracking."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.fixtures.config import make_wallpanel_control_settings
from wallpanel_control.adapters.fake import FakeWallpanel
from wallpanel_control.devices.probe import ACTION_TOPIC, PanelProbe
from wallpanel_control.devices.restore import LastAnswers
from wallpanel_control.devices.system import SystemActionState


@pytest.mark.unit
class TestActionRevisionTracking:
    async def test_action_during_terminal_publish_is_processed(self) -> None:
        """A later acknowledgement is not absorbed by an earlier publish."""
        answers = LastAnswers()
        first = SystemActionState(accepted=True, action="wake", observed="pending")
        answers.record(ACTION_TOPIC, first, accepted_at=0)

        entered_publish = asyncio.Event()
        finish_publish = asyncio.Event()

        async def blocked_publish(*_args: object, **_kwargs: object) -> None:
            entered_publish.set()
            await finish_publish.wait()

        ctx = MagicMock()
        ctx.clock.now.return_value = 1
        ctx.publish = AsyncMock(side_effect=blocked_publish)
        probe = PanelProbe(
            ctx,
            FakeWallpanel(),
            make_wallpanel_control_settings(),
            answers,
        )
        probe._action_revision = answers.revision(ACTION_TOPIC)

        publishing = asyncio.create_task(probe._finish(first, "confirmed"))
        await entered_publish.wait()
        second = SystemActionState(accepted=True, action="wake", observed="pending")
        answers.record(ACTION_TOPIC, second, accepted_at=1)
        second_revision = answers.revision(ACTION_TOPIC)
        finish_publish.set()
        await publishing

        await probe._resolve_action(reachable=False)

        assert probe._action_revision == second_revision
        assert probe._pending is not None
        assert probe._pending[0] == second
