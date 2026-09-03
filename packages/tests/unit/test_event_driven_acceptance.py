"""Downstream acceptance for cosalette 0.8.0 event-driven publication (cap-8au).

Checks the sixteen validation criteria of
``docs/planning/cosalette-event-driven-publication-proposal.md`` against the
shipped 0.8.0 wheel.  The criteria are framework contracts, not app behaviour,
so they are asserted here against purpose-built minimal apps rather than in
either adopting app's suite — an assertion phrased in terms of a bulb or a
LaCrosse frame would be answering a different question.

The two app-shaped acceptance items live where the app does:

* jeelink2mqtt publishes within the same virtual tick as the frame —
  ``apps/jeelink2mqtt/packages/tests/integration/test_event_driven_acceptance.py``
* wiz2mqtt publishes from a push without the tick elapsing —
  ``apps/wiz2mqtt/packages/tests/integration/test_bulb_state_publication.py``
  (``TestPushDrivenPublication``)

Criterion 16 is restated rather than checked as written.  It asked whether the
``triggerable`` + ``group=`` and ``triggerable``-on-root registration guards
still applied; 0.8.0 lifted both (ADR-067 group wake, ADR-064 root local
source), so the new behaviour is asserted instead.  See
``docs/planning/cosalette-event-driven-publication-acceptance.md`` for the
criterion-by-criterion verdicts, including the two that source reading rather
than a test settles.

Test Techniques Used:
- Specification-based: each test names the proposal criterion it discharges
- Equivalence Partitioning: woken run vs ticked run, as the parity axis
- State Transition Testing: availability offline → online across woken runs
- Negative control: a quiet window proves the long interval is unreachable,
  so "a publish happened" cannot be a heartbeat in disguise
- Cross-check: AsyncAPI and HA discovery output compared with and without
  local triggering, from the same registrations
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any

import pytest
from cosalette import (
    App,
    DeviceContext,
    EntityNotifier,
    MockMqttClient,
    OnChange,
    Settings,
    UnknownEntityError,
)
from cosalette.schema import consumer
from cosalette.stores import MemoryStore
from cosalette.testing import (
    AppHarness,
    FakeClock,
    assert_discovery_topics_published,
    make_settings,
)
from pydantic import BaseModel, Field

pytestmark = pytest.mark.unit

APP_NAME = "acceptance"
"""Topic prefix for every app built here."""

ENTITIES = ("kitchen", "office", "hall")
"""Three expanded names, so "only the named entity wakes" has two controls."""

WOKEN = ENTITIES[0]
"""The entity every notify test arms."""

NO_TICK_INTERVAL = 3600.0
"""An interval no test window can reach — see :class:`RealSleepClock`."""

_IN_FLIGHT_SECONDS = 0.05
"""How long the coalescing handler stays busy, so arms land mid-run."""

_SETTLE_SECONDS = 0.25
"""Real seconds to let every consequence of an arm play out."""

_QUIET_SECONDS = 0.2
"""Deliberate inactivity used to prove no scheduled tick is due."""

_WAIT_TIMEOUT = 2.0
"""How long :func:`_wait_until` polls before calling a condition failed."""

_FAST_TICK_SECONDS = 0.02
"""A genuinely short interval, for the ticked half of a parity comparison."""

_VOLATILE_ERROR_FIELDS = ("timestamp", "id")
"""Error-payload fields that differ between two runs by construction."""

_FAILURE_RUNS = 3
"""Consecutive failures compared between a woken and a ticked entity."""


class RealSleepClock(FakeClock):
    """A :class:`FakeClock` whose ``sleep`` actually waits.

    ``FakeClock.sleep`` advances *virtual* time with no real delay, so
    ``interval=3600`` collapses into a busy loop that races the virtual
    clock forward and "published without the clock advancing" becomes
    unfalsifiable.  Sleeping for real makes :data:`NO_TICK_INTERVAL`
    genuinely unreachable inside a test, so ``now()`` stays where the
    test left it and a publish that does arrive can only have been woken.

    A fourth copy of this class (airthings2mqtt, caldates2mqtt and
    wiz2mqtt each hand-rolled one).  Giving it a single home is cap-o9x;
    this module is one of the sites that task has to collect.
    """

    async def sleep(self, seconds: float) -> None:
        """Sleep for *seconds* of wall-clock time, keeping ``now()`` in step."""
        await asyncio.sleep(seconds)
        if seconds > 0:
            self._time += seconds


class StateModel(BaseModel):
    """Return model for the ``state_model=`` validation criterion."""

    reading: int


class AnnotatedStateModel(BaseModel):
    """Return model carrying a ``consumer()`` annotation for HA discovery."""

    reading: Annotated[
        int,
        Field(
            json_schema_extra=consumer(
                display_name="Reading", unit="°C", state_class="measurement"
            )
        ),
    ]


class Recorder:
    """What a handler did, and what the next run should do.

    One instance per app.  ``entries`` counts handler *entry* — the
    coalescing criterion needs runs that started, not runs that
    published — while the remaining attributes let a test steer the next
    run without rebuilding the app.
    """

    def __init__(self) -> None:
        self.entries: dict[str, int] = dict.fromkeys(ENTITIES, 0)
        self.payloads: dict[str, dict[str, Any]] = {
            name: {"reading": 0} for name in ENTITIES
        }
        self.in_flight_seconds: float = 0.0
        self.unavailable: bool = False
        self.raise_next: Exception | None = None

    def total_entries(self) -> int:
        """Handler entries across every entity."""
        return sum(self.entries.values())


def _name_map(_settings: Settings) -> dict[str, str]:
    """Callable ``NameSpec`` expanding to :data:`ENTITIES`."""
    return {name: name for name in ENTITIES}


def build_app(
    recorder: Recorder,
    *,
    triggerable: str | bool = "local",
    interval: float = NO_TICK_INTERVAL,
    state_model: type[BaseModel] | None = None,
    publish: Any = None,
    discovery: bool = False,
    notifier_sink: list[EntityNotifier] | None = None,
) -> App:
    """A minimal three-entity telemetry app, parameterised by what is asserted.

    Every criterion is a question about *one* registration knob, so the
    same builder serves them all: ``triggerable=`` for the with/without
    comparisons, ``state_model=`` for return validation, ``discovery=``
    for the HA non-regression pair.

    *notifier_sink* receives the framework's :class:`EntityNotifier` as a
    side effect of the state factory running — the supported way to reach
    the handle a test needs to arm.
    """
    app = App(name=APP_NAME, version="1.0.0", store=MemoryStore())

    @app.state
    def _recorder(notify: EntityNotifier) -> Recorder:
        if notifier_sink is not None:
            notifier_sink.append(notify)
        return recorder

    @app.telemetry(
        name=_name_map,
        interval=interval,
        triggerable=triggerable,
        state_model=state_model,
        publish=publish if publish is not None else OnChange(),
        summary="Acceptance telemetry entity",
    )
    async def entity(
        ctx: DeviceContext, config: str, state: Recorder
    ) -> dict[str, Any] | None:
        state.entries[config] += 1
        if state.in_flight_seconds:
            await asyncio.sleep(state.in_flight_seconds)
        if state.raise_next is not None:
            raise state.raise_next
        if state.unavailable:
            await ctx.mark_unavailable()
            return None
        await ctx.mark_available()
        return dict(state.payloads[config])

    if discovery:
        app.discovery()
    return app


def build_harness(app: App, *, real_sleep: bool = True) -> AppHarness:
    """Wrap *app* in a harness whose clock only moves when something sleeps."""
    return AppHarness(
        app=app,
        mqtt=MockMqttClient(),
        clock=RealSleepClock() if real_sleep else FakeClock(),
        settings=make_settings(),
        shutdown_event=asyncio.Event(),
    )


async def _wait_until(condition: Callable[[], bool], what: str) -> None:
    """Poll *condition* until true, or fail naming *what* was awaited."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _WAIT_TIMEOUT
    while not condition():
        if loop.time() >= deadline:
            raise AssertionError(f"timed out after {_WAIT_TIMEOUT}s waiting for {what}")
        await asyncio.sleep(0.005)


@contextlib.asynccontextmanager
async def running(harness: AppHarness) -> AsyncIterator[AppHarness]:
    """Run *harness* until every entity has completed its startup run."""
    task = asyncio.create_task(harness.run())
    try:
        await _wait_until(
            lambda: len(state_messages(harness)) == len(ENTITIES),
            "the startup run of every entity",
        )
        yield harness
    finally:
        harness.shutdown_event.set()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


def state_topic(name: str) -> str:
    """The state topic the proposal says a woken entity must publish to."""
    return f"{APP_NAME}/{name}/state"


def state_messages(harness: AppHarness, name: str | None = None) -> list[Any]:
    """Recorded state messages, for one entity or all of them."""
    if name is not None:
        return harness.messages_for(state_topic(name))
    return [m for n in ENTITIES for m in harness.messages_for(state_topic(n))]


def topics(harness: AppHarness) -> set[str]:
    """Distinct topics published so far."""
    return {topic for topic, *_ in harness.published()}


def error_topic(name: str) -> str:
    """The topic the framework publishes a failed cycle to."""
    return f"{APP_NAME}/{name}/error"


def _stable_error(payload: str) -> dict[str, Any]:
    """An error payload with the fields that cannot match stripped out."""
    parsed = json.loads(payload)
    for field in _VOLATILE_ERROR_FIELDS:
        parsed.pop(field, None)
    return parsed


async def _registry_document(app: App) -> str:
    """The retained ``_meta/registry`` payload an app publishes on connect."""
    harness = build_harness(app)
    async with running(harness):
        messages = harness.messages_for(f"{APP_NAME}/_meta/registry")
    assert messages, "the app published no registry document"
    return messages[0][0]


async def _discovery_configs(app: App) -> dict[str, dict[str, Any]]:
    """Retained HA discovery ``config`` topic → payload, for a discovery app."""
    harness = build_harness(app)
    async with running(harness):
        await _wait_until(
            lambda: any(t.endswith("/config") for t in topics(harness)),
            "a retained HA discovery config topic",
        )
        return {
            topic: json.loads(harness.messages_for(topic)[0][0])
            for topic in sorted(topics(harness))
            if topic.endswith("/config")
        }


_ROOT_NAME = "root_entity"
"""An unnamed (root) entity is keyed by its handler name in the registry."""


def _build_root_app(
    recorder: Recorder,
    triggerable: str | bool,
    notifier_sink: list[EntityNotifier],
) -> App:
    """A single root (unnamed) telemetry entity — no ``name=`` at all."""
    app = App(name=APP_NAME, version="1.0.0", store=MemoryStore())

    @app.state
    def _recorder(notify: EntityNotifier) -> Recorder:
        notifier_sink.append(notify)
        return recorder

    @app.telemetry(
        interval=NO_TICK_INTERVAL,
        triggerable=triggerable,
        publish=OnChange(),
        summary="Root acceptance entity",
    )
    async def root_entity(ctx: DeviceContext, state: Recorder) -> dict[str, Any]:
        state.entries[WOKEN] += 1
        return dict(state.payloads[WOKEN])

    return app


_APPS_DIR = Path(__file__).resolve().parents[3] / "apps"
"""The monorepo's app root — this file is packages/tests/unit/<name>.py."""


def _app_dirs() -> list[str]:
    """Every app directory in the monorepo."""
    return sorted(path.name for path in _APPS_DIR.iterdir() if path.is_dir())


def _trigger_sources(app_dir: str) -> set[str]:
    """Normalised trigger sources declared by one app's registrations.

    Read from the live ``App`` object rather than from source text: a
    ``triggerable=`` written in a docstring is documentation, and three
    apps that never adopted anything mention one.
    """
    module = import_module(f"{app_dir.replace('-', '_')}.main")
    app: App = module.app
    return {
        reg.triggerable
        for reg in (*app._telemetry, *app._devices)
        if reg.triggerable is not None
    }


def _apps_declaring(source: str) -> set[str]:
    """App directories with at least one registration of trigger *source*."""
    return {name for name in _app_dirs() if source in _trigger_sources(name)}


def _throttled_apps() -> set[str]:
    """App directories that bound a trigger-initiated run with ``min_interval=``."""
    throttled: set[str] = set()
    for name in _app_dirs():
        module = import_module(f"{name.replace('-', '_')}.main")
        app: App = module.app
        if any(
            reg.triggerable is not None and reg.min_interval is not None
            for reg in (*app._telemetry, *app._devices)
        ):
            throttled.add(name)
    return throttled


def _build_discovery_app(
    recorder: Recorder, *, triggerable: str | bool = "local"
) -> App:
    """Three entities whose annotated return model drives HA discovery.

    The discovery generator reads the channel payload schema, which comes
    from the handler's *return annotation* — so the model has to be
    annotated here rather than passed as ``state_model=``.
    """
    app = App(name=APP_NAME, version="1.0.0", store=MemoryStore())

    @app.state
    def _recorder(notify: EntityNotifier) -> Recorder:
        return recorder

    @app.telemetry(
        name=_name_map,
        interval=NO_TICK_INTERVAL,
        triggerable=triggerable,
        publish=OnChange(),
        summary="Discovery acceptance entity",
    )
    async def entity(
        ctx: DeviceContext, config: str, state: Recorder
    ) -> AnnotatedStateModel:
        state.entries[config] += 1
        return AnnotatedStateModel(**state.payloads[config])

    app.discovery()
    return app


def _build_grouped_app(recorder: Recorder, notifier_sink: list[EntityNotifier]) -> App:
    """Three locally-triggerable entities sharing one coalescing group."""
    app = App(name=APP_NAME, version="1.0.0", store=MemoryStore())

    @app.state
    def _recorder(notify: EntityNotifier) -> Recorder:
        notifier_sink.append(notify)
        return recorder

    @app.telemetry(
        name=_name_map,
        interval=NO_TICK_INTERVAL,
        triggerable="local",
        group="shared",
        publish=OnChange(),
        summary="Grouped acceptance entity",
    )
    async def entity(
        ctx: DeviceContext, config: str, state: Recorder
    ) -> dict[str, Any]:
        state.entries[config] += 1
        return dict(state.payloads[config])

    return app


@pytest.fixture
def recorder() -> Recorder:
    """A fresh handler recorder."""
    return Recorder()


@pytest.fixture
def notifier_sink() -> list[EntityNotifier]:
    """Collects the framework's notifier when the state factory runs."""
    return []


@pytest.fixture
def harness(recorder: Recorder, notifier_sink: list[EntityNotifier]) -> AppHarness:
    """Three locally-triggerable entities on an unreachable interval."""
    return build_harness(build_app(recorder, notifier_sink=notifier_sink))


@pytest.fixture
def notify(notifier_sink: list[EntityNotifier]) -> Callable[[str], None]:
    """Arm an entity through the framework's own notifier handle."""

    def _notify(name: str) -> None:
        assert notifier_sink, "the state factory has not run — app not started yet"
        notifier_sink[0](name)

    return _notify


class TestCoreBehaviour:
    """Criteria 1-6 — what the local trigger source must do."""

    async def test_one_slot_per_expanded_entity(
        self, harness: AppHarness, notifier_sink: list[EntityNotifier]
    ) -> None:
        """Criterion 1: a slot exists per expanded entity, and no more.

        The proposal phrased this over ``TriggerConfig.build(...).slots``,
        an internal.  ``EntityNotifier.entities`` is the public projection
        of exactly that mapping — the names the handle can wake — so it is
        asserted here instead.

        Technique: Specification-based — expansion count is the contract.
        """
        async with running(harness):
            assert notifier_sink[0].entities == frozenset(ENTITIES)
            assert len(notifier_sink[0].entities) == len(ENTITIES)

    async def test_a_notify_publishes_without_the_clock_advancing(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 2: the assertion the whole proposal exists for.

        Technique: Specification-based — one publish, virtual time unmoved.
        """
        async with running(harness):
            started_at = harness.clock.now()
            recorder.payloads[WOKEN] = {"reading": 1}

            notify(WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the woken publish on {state_topic(WOKEN)}",
            )

            assert harness.clock.now() == started_at
            payload, _retain, _qos = state_messages(harness, WOKEN)[1]
            assert json.loads(payload)["reading"] == 1

    async def test_the_unreachable_interval_really_holds(
        self, harness: AppHarness, recorder: Recorder
    ) -> None:
        """The negative control for every notify test in this module.

        Without it, a second publish could be a fast scheduled tick and
        every "woken" assertion above would be vacuous.

        Technique: Negative control — no arm, no publish, no time passing.
        """
        async with running(harness):
            recorder.payloads[WOKEN] = {"reading": 1}
            await asyncio.sleep(_QUIET_SECONDS)

            assert len(state_messages(harness, WOKEN)) == 1
            assert harness.clock.now() == 0.0

    async def test_only_the_named_entity_wakes(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 3: notifying one name leaves its siblings untouched.

        Technique: Equivalence Partitioning — named entity vs the other two.
        """
        async with running(harness):
            for name in ENTITIES:
                recorder.payloads[name] = {"reading": 1}
            entries_before = dict(recorder.entries)

            notify(WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the woken publish on {state_topic(WOKEN)}",
            )
            await asyncio.sleep(_QUIET_SECONDS)

            assert recorder.entries[WOKEN] == entries_before[WOKEN] + 1
            for name in ENTITIES[1:]:
                assert recorder.entries[name] == entries_before[name]
                assert len(state_messages(harness, name)) == 1

    async def test_arms_landing_mid_run_coalesce_into_one_rerun(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 4: k arms delivered in-flight produce exactly one re-run.

        Technique: Boundary — five arms inside one busy window, one re-run.
        """
        async with running(harness):
            recorder.in_flight_seconds = _IN_FLIGHT_SECONDS
            entries_before = recorder.entries[WOKEN]

            notify(WOKEN)
            await _wait_until(
                lambda: recorder.entries[WOKEN] == entries_before + 1,
                "the woken run to enter the handler",
            )
            for _ in range(5):
                notify(WOKEN)
            await asyncio.sleep(_SETTLE_SECONDS)

            assert recorder.entries[WOKEN] == entries_before + 2

    async def test_an_unknown_name_fails_loudly(
        self, harness: AppHarness, notify: Callable[[str], None]
    ) -> None:
        """Criterion 5: an unknown name raises, and never silently no-ops.

        Technique: Error Guessing — a typo'd or pre-expansion name.
        """
        async with running(harness):
            with pytest.raises(UnknownEntityError, match="ghost"):
                notify("ghost")

    async def test_an_arm_from_another_thread_is_delivered_once(
        self,
        harness: AppHarness,
        recorder: Recorder,
        notifier_sink: list[EntityNotifier],
    ) -> None:
        """Criterion 6: an off-loop arm is delivered exactly once, and does not raise.

        Technique: Specification-based — the ADR-042 marshalling contract.
        """
        async with running(harness):
            recorder.payloads[WOKEN] = {"reading": 1}
            entries_before = recorder.entries[WOKEN]

            await asyncio.to_thread(notifier_sink[0], WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the off-loop publish on {state_topic(WOKEN)}",
            )
            await asyncio.sleep(_QUIET_SECONDS)

            assert recorder.entries[WOKEN] == entries_before + 1

    async def test_an_off_loop_bad_name_raises_in_the_calling_thread(
        self, harness: AppHarness, notifier_sink: list[EntityNotifier]
    ) -> None:
        """Criterion 6, second half: the name is validated before marshalling.

        A name checked on the loop instead would surface as an unretrievable
        exception inside ``call_soon_threadsafe``, which is the silent no-op
        criterion 5 exists to forbid.

        Technique: Error Guessing — bad name on the thread-safe path.
        """
        async with running(harness):
            with pytest.raises(UnknownEntityError, match="ghost"):
                await asyncio.to_thread(notifier_sink[0], "ghost")


class TestParity:
    """Criteria 7-10 — nothing about a woken run differs from a ticked run."""

    async def test_on_change_still_gates_a_woken_run(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 7: an identical payload from a wake is still deduped.

        Technique: Equivalence Partitioning — unchanged vs changed payload
        across two wakes of the same entity.
        """
        async with running(harness):
            notify(WOKEN)
            notify(WOKEN)
            await asyncio.sleep(_SETTLE_SECONDS)
            assert len(state_messages(harness, WOKEN)) == 1, (
                "OnChange() let an unchanged payload through on a woken run"
            )

            recorder.payloads[WOKEN] = {"reading": 1}
            notify(WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                "the changed payload to publish",
            )

    async def test_return_validation_treats_a_woken_run_like_a_ticked_one(
        self, recorder: Recorder, notifier_sink: list[EntityNotifier]
    ) -> None:
        """Criterion 8: return validation is blind to how the run was woken.

        The criterion as written ("a woken run returning a non-conforming
        payload raises ``ReturnValidationError`` and publishes to the error
        topic") asserts two things at once, and only the second half is
        about event-driven publication.  The first half does not hold in
        0.8.0 for *any* wake reason — see
        :meth:`test_a_dict_return_bypasses_the_declared_state_model` — so
        parity is asserted here against the failure mode that does raise.

        Technique: Equivalence Partitioning — woken run vs ticked run,
        same handler, same non-serialisable return.
        """
        woken = build_harness(
            build_app(recorder, state_model=StateModel, notifier_sink=notifier_sink)
        )
        async with running(woken):
            recorder.payloads[WOKEN] = {"reading": object()}  # type: ignore[dict-item]
            notifier_sink[0](WOKEN)
            await _wait_until(
                lambda: bool(woken.messages_for(error_topic(WOKEN))),
                f"an error publish on {error_topic(WOKEN)}",
            )
            woken_errors = [
                _stable_error(payload)
                for payload, *_ in woken.messages_for(error_topic(WOKEN))
            ]
            assert len(state_messages(woken, WOKEN)) == 1, (
                "a payload that failed validation reached the state topic"
            )

        ticked_recorder = Recorder()
        ticked_recorder.payloads[WOKEN] = {"reading": object()}  # type: ignore[dict-item]
        ticked = build_harness(
            build_app(
                ticked_recorder,
                triggerable=False,
                interval=_FAST_TICK_SECONDS,
                state_model=StateModel,
            )
        )
        task = asyncio.create_task(ticked.run())
        try:
            await _wait_until(
                lambda: bool(ticked.messages_for(error_topic(WOKEN))),
                f"a ticked error publish on {error_topic(WOKEN)}",
            )
            ticked_errors = [
                _stable_error(payload)
                for payload, *_ in ticked.messages_for(error_topic(WOKEN))
            ]
        finally:
            ticked.shutdown_event.set()
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)

        assert woken_errors[0] == ticked_errors[0]

    async def test_a_dict_return_bypasses_the_declared_state_model(
        self, recorder: Recorder, notifier_sink: list[EntityNotifier]
    ) -> None:
        """A plain-``dict`` telemetry return is never validated — cap-8au finding.

        ``normalize_return`` tries ``TypeAdapter(model).dump_python(value)``
        first and only falls back to ``validate_python`` when that raises
        (``_runners/_contracts.py:288-296``).  Pydantic serialises a plain
        dict against a ``BaseModel`` adapter with a ``UserWarning`` rather
        than an exception, so the fallback never runs and a field of the
        wrong type is published unchallenged.

        Predates 0.8.0 and applies to ticked and woken runs alike, so it
        is not a regression of event-driven publication — but criterion 8
        asked, and this is the answer.  Tracked upstream as cap-b8h.  The
        ``@app.device`` archetype is unaffected: its ``state_model`` is
        threaded onto the context (``_wiring/_context.py:120``) and
        ``publish_state`` validates directly, which is the path
        jeelink2mqtt's ``sensor_entity`` takes.

        Technique: Error Guessing — the wrong field type, the shape a
        handler most often returns.
        """
        harness = build_harness(
            build_app(recorder, state_model=StateModel, notifier_sink=notifier_sink)
        )
        async with running(harness):
            recorder.payloads[WOKEN] = {"reading": "not-an-int"}

            notifier_sink[0](WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the woken publish on {state_topic(WOKEN)}",
            )

            payload, _retain, _qos = state_messages(harness, WOKEN)[1]
            assert json.loads(payload) == {"reading": "not-an-int"}
            assert not harness.messages_for(error_topic(WOKEN))

    async def test_availability_is_unchanged_on_a_woken_run(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 9: mark_unavailable/mark_available behave as from a tick.

        Technique: State Transition — online → offline → online, all woken.
        """
        availability = f"{APP_NAME}/{WOKEN}/availability"
        async with running(harness):
            recorder.unavailable = True
            notify(WOKEN)
            await _wait_until(
                lambda: any(
                    "offline" in payload
                    for payload, *_ in harness.messages_for(availability)
                ),
                f"an offline publish on {availability}",
            )

            recorder.unavailable = False
            recorder.payloads[WOKEN] = {"reading": 1}
            notify(WOKEN)
            await _wait_until(
                lambda: "online" in harness.messages_for(availability)[-1][0],
                f"the recovery publish on {availability}",
            )

            for _payload, retain, _qos in harness.messages_for(availability):
                assert retain is True

    async def test_a_woken_entity_publishes_to_its_own_state_topic(
        self, harness: AppHarness, recorder: Recorder, notify: Callable[[str], None]
    ) -> None:
        """Criterion 10: no sub-topic appears for a woken publish.

        Asserted through the harness's recorded topics rather than by
        inspecting the router, as the criterion requires.

        Technique: Golden set — the exact topic set for one entity.
        """
        async with running(harness):
            recorder.payloads[WOKEN] = {"reading": 1}
            notify(WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the woken publish on {state_topic(WOKEN)}",
            )

            prefix = f"{APP_NAME}/{WOKEN}/"
            entity_topics = {t for t in topics(harness) if t.startswith(prefix)}
            assert entity_topics == {
                state_topic(WOKEN),
                f"{APP_NAME}/{WOKEN}/availability",
            }


class TestNonRegression:
    """Criteria 11-13 — the ADR-004 discovery path must not move."""

    async def test_asyncapi_is_identical_with_and_without_local_triggering(
        self, recorder: Recorder
    ) -> None:
        """Criterion 11: the published registry document does not move.

        Compared as the retained ``_meta/registry`` payload rather than a
        pre-run ``app.asyncapi()`` call, so the comparison is of the
        post-expand document an operator actually receives.

        Technique: Cross-check — same registrations, one knob apart.
        """
        with_local = await _registry_document(build_app(recorder))
        without = await _registry_document(build_app(Recorder(), triggerable=False))

        assert with_local == without

    async def test_discovery_config_topics_are_identical(
        self, recorder: Recorder
    ) -> None:
        """Criterion 12: the retained HA config topic set does not move.

        Technique: Golden set — the exact discovery topic → payload map.
        """
        with_local = await _discovery_configs(_build_discovery_app(recorder))
        without = await _discovery_configs(
            _build_discovery_app(Recorder(), triggerable=False)
        )

        assert with_local
        assert with_local == without

    async def test_discovery_topics_still_cross_check_against_runtime(
        self, recorder: Recorder
    ) -> None:
        """Criterion 12, second half: the framework's own assertion still passes.

        The expected payloads are taken from the app *without* local
        triggering, then checked against the runtime topics of the app
        *with* it — so the helper is answering a cross-app question, not
        comparing an app to itself.

        Technique: Cross-check — schema-derived expectation vs runtime truth.
        """
        expected = [
            SimpleNamespace(config=config)
            for config in (
                await _discovery_configs(
                    _build_discovery_app(Recorder(), triggerable=False)
                )
            ).values()
        ]

        harness = build_harness(_build_discovery_app(recorder))
        async with running(harness):
            assert_discovery_topics_published(harness, expected)

    async def test_consumer_annotations_survive_local_triggering(
        self, recorder: Recorder
    ) -> None:
        """Criterion 13: cadence and annotation stay on different axes.

        Technique: Specification-based — the annotation reaches the payload
        whether or not the entity is locally triggerable.
        """
        configs = await _discovery_configs(_build_discovery_app(recorder))

        annotated = [c for c in configs.values() if c.get("name") == "Reading"]
        assert annotated, f"no consumer()-derived entity in {sorted(configs)}"
        assert annotated[0]["unit_of_measurement"] == "°C"
        assert annotated[0]["state_class"] == "measurement"


class TestBackwardCompatibility:
    """Criteria 14-16 — what 0.8.0 kept, and what it deliberately lifted."""

    async def test_triggerable_true_still_means_mqtt(
        self, recorder: Recorder, notifier_sink: list[EntityNotifier]
    ) -> None:
        """Criterion 14: ``True`` is still the permanent alias for ``'mqtt'``.

        Technique: Specification-based — the router's subscription set is
        the observable meaning of "MQTT-triggerable".
        """
        harness = build_harness(
            build_app(recorder, triggerable=True, notifier_sink=notifier_sink)
        )
        async with running(harness):
            for name in ENTITIES:
                assert f"{APP_NAME}/{name}/set" in harness.mqtt.subscriptions

            assert notifier_sink[0].entities == frozenset(), (
                "an MQTT-only entity was given a local arming path"
            )
            with pytest.raises(UnknownEntityError):
                notifier_sink[0](WOKEN)

    async def test_a_local_source_subscribes_nothing(self, harness: AppHarness) -> None:
        """Criterion 14's other half: ``'local'`` adds no MQTT surface.

        This is what keeps criteria 11-13 true — an adopting app's
        subscription set and generated documents are the same as before.

        Technique: Negative control — no trigger topic appears.
        """
        async with running(harness):
            assert not [
                topic for topic in harness.mqtt.subscriptions if "/set" in topic
            ]

    async def test_local_triggering_is_allowed_on_a_root_entity(self) -> None:
        """Criterion 16 restated (ADR-064): the root-device guard was lifted.

        The proposal's open question 4 asked whether the ``triggerable``
        restriction on an unnamed device applied to a local source.  It
        does not — a local wake needs no topic segment — while an MQTT
        source on a root entity is still rejected, now at registration.

        Technique: Decision Table — root × (local | mqtt).
        """
        recorder, sink = Recorder(), []
        harness = build_harness(_build_root_app(recorder, "local", sink))
        task = asyncio.create_task(harness.run())
        try:
            await _wait_until(
                lambda: bool(harness.messages_for(f"{APP_NAME}/state")),
                f"the root entity's publish on {APP_NAME}/state",
            )
            assert sink[0].entities == frozenset({_ROOT_NAME})
        finally:
            harness.shutdown_event.set()
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)

        with pytest.raises(ValueError, match="requires a named device"):
            _build_root_app(Recorder(), True, [])

    async def test_local_triggering_coexists_with_a_coalescing_group(self) -> None:
        """Criterion 16 restated (ADR-067): the ``group=`` exclusion was lifted.

        Open question 6 asked whether a local source inherits the
        ``triggerable``/``group=`` mutual exclusion.  It does not: an arm
        reaches the group scheduler through the group's shared wake event.

        Technique: Decision Table — local × grouped.
        """
        recorder, sink = Recorder(), []
        harness = build_harness(_build_grouped_app(recorder, sink))
        async with running(harness):
            recorder.payloads[WOKEN] = {"reading": 1}
            entries_before = recorder.entries[WOKEN]

            sink[0](WOKEN)
            await _wait_until(
                lambda: len(state_messages(harness, WOKEN)) == 2,
                f"the woken publish on {state_topic(WOKEN)} of a grouped entity",
            )

            assert recorder.entries[WOKEN] > entries_before
            assert harness.clock.now() == 0.0


class TestHealthAccounting:
    """Open question 7 — a woken run must count exactly as a ticked one.

    The proposal recorded this as *believed but not verified*: the runner
    path looked shared, but was not read end to end.  It now has been.
    ``woke_by_trigger`` is carried through ``_run_single_telemetry`` for
    one purpose — ``_update_trigger_kwargs`` (``_telemetry_runner.py:380``),
    which injects the ``TriggerPayload`` a handler may declare.  Every
    step after the handler returns (``_execute_cycle_attempt`` →
    ``_process_cycle_result`` → ``_handle_telemetry_outcome`` /
    ``_handle_telemetry_error`` → ``health_reporter.set_device_status``
    and ``_circuit_breaker_record``) receives no wake reason and cannot
    branch on one.

    The heartbeat that carries device status to ``{prefix}/status`` is
    published on a cadence no unit-scale window reaches, so the assertion
    below is on the observable the framework emits per failed cycle
    instead: the error publication itself.
    """

    async def test_a_failing_woken_run_reports_what_a_failing_tick_reports(
        self, recorder: Recorder, notifier_sink: list[EntityNotifier]
    ) -> None:
        """A wake reason changes nothing about how a failure is accounted for.

        Three consecutive identical failures must produce one error
        publication, not three — the runner carries ``last_error_type``
        across cycles and only republishes on a change.  That the count
        and the payload match on both paths is the accounting parity the
        open question asked about.

        Technique: Equivalence Partitioning — the same handler failure,
        reached once by a wake and once by a scheduled tick.
        """
        woken = build_harness(build_app(recorder, notifier_sink=notifier_sink))
        async with running(woken):
            recorder.raise_next = RuntimeError("boom")
            entries_before = recorder.entries[WOKEN]
            for _ in range(_FAILURE_RUNS):
                notifier_sink[0](WOKEN)
                await asyncio.sleep(_IN_FLIGHT_SECONDS)
            await _wait_until(
                lambda: recorder.entries[WOKEN] >= entries_before + _FAILURE_RUNS,
                f"{_FAILURE_RUNS} woken failures",
            )
            woken_errors = [
                _stable_error(payload)
                for payload, *_ in woken.messages_for(error_topic(WOKEN))
            ]
            woken_availability = list(
                woken.messages_for(f"{APP_NAME}/{WOKEN}/availability")
            )

        ticked_recorder = Recorder()
        ticked = build_harness(
            build_app(ticked_recorder, triggerable=False, interval=_FAST_TICK_SECONDS)
        )
        task = asyncio.create_task(ticked.run())
        try:
            # Let one cycle succeed first, so both entities reach the
            # failures from the same online state — otherwise the
            # comparison is between an entity that came online and one
            # that never did.
            await _wait_until(
                lambda: len(state_messages(ticked, WOKEN)) == 1,
                "the ticked entity's startup run",
            )
            ticked_recorder.raise_next = RuntimeError("boom")
            entered_at = ticked_recorder.entries[WOKEN]
            await _wait_until(
                lambda: ticked_recorder.entries[WOKEN] >= entered_at + _FAILURE_RUNS,
                f"{_FAILURE_RUNS} ticked failures",
            )
            ticked_errors = [
                _stable_error(payload)
                for payload, *_ in ticked.messages_for(error_topic(WOKEN))
            ]
            ticked_availability = list(
                ticked.messages_for(f"{APP_NAME}/{WOKEN}/availability")
            )
        finally:
            ticked.shutdown_event.set()
            await asyncio.wait_for(task, timeout=_WAIT_TIMEOUT)

        assert len(woken_errors) == 1, "a woken failure republished on every cycle"
        assert woken_errors == ticked_errors
        assert woken_availability == ticked_availability


class TestAdoptionSet:
    """Criterion 15 — an app that does not opt in sees no change.

    The framework half is the upstream suite passing unmodified.  The
    downstream half is that the trigger sources declared across the
    monorepo are exactly the accepted ones: a fourth app acquiring a
    local source without its own acceptance, or an app quietly gaining
    an MQTT trigger topic, is the regression this guards.

    The golden sets below are ADR-005's own per-app verdict table, read
    back off the live ``App`` objects.  Note that the adoption set is
    wider than cap-8au's acceptance criteria name: vito2mqtt registers
    all seven Optolink signal groups ``triggerable="local"`` alongside
    ``group="optolink"`` and ``min_interval=`` (``_registration.py:71-78``)
    — the production instance of the ADR-067 guard criterion 16 restates.
    """

    LOCAL_ADOPTERS = {"jeelink2mqtt", "vito2mqtt", "wiz2mqtt"}
    MQTT_TRIGGERABLE = {"airthings2mqtt", "caldates2mqtt"}
    THROTTLED = {"airthings2mqtt", "caldates2mqtt", "vito2mqtt"}

    def test_the_local_adoption_set_is_exactly_the_accepted_apps(self) -> None:
        """Technique: Golden set — the exact set of local adopters."""
        assert _apps_declaring("local") == self.LOCAL_ADOPTERS

    def test_no_app_declares_a_both_source(self) -> None:
        """``'both'`` would add an MQTT trigger topic to an adopting app.

        Technique: Negative control — the source nothing accepted.
        """
        assert _apps_declaring("both") == set()

    def test_pre_existing_mqtt_triggers_are_untouched(self) -> None:
        """Criterion 14 in production: ``triggerable=True`` still means MQTT.

        Both apps predate the local source and still normalise to
        ``'mqtt'``, so their subscription sets are what they were.

        Technique: Golden set — the exact set of MQTT-triggerable apps.
        """
        assert _apps_declaring("mqtt") == self.MQTT_TRIGGERABLE

    def test_every_other_app_declares_no_trigger_source(self) -> None:
        """Technique: Equivalence Partitioning — the untouched remainder."""
        adopters = self.LOCAL_ADOPTERS | self.MQTT_TRIGGERABLE
        for app_dir in _app_dirs():
            if app_dir not in adopters:
                assert _trigger_sources(app_dir) == set(), app_dir

    def test_the_min_interval_rule_matches_the_adr(self) -> None:
        """ADR-005's throttle rule, asserted rather than only written down.

        A throttle goes where a wake costs a real round trip on a shared
        or remote resource, and deliberately *not* where ``OnChange()``
        already gates duplicates (wiz2mqtt) or where a ``DeviceTrigger``
        reads a ``"scheduled"`` return as "nothing arrived" (jeelink2mqtt)
        — a throttle silently breaks that reading.

        Values are not pinned here: cap-9hn may make them per-deployment,
        which changes the numbers but not which apps carry one.

        Technique: Golden set — the exact set of throttled apps.
        """
        assert _throttled_apps() == self.THROTTLED
