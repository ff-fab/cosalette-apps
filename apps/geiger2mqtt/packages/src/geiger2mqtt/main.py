"""Entry point for geiger2mqtt."""

from __future__ import annotations

from collections.abc import Callable

import cosalette
from cosalette import setting_ref

from geiger2mqtt import __version__
from geiger2mqtt.adapters.fake import fake_pulse_counter
from geiger2mqtt.devices.radiation import NoPulseError, RadiationState, radiation
from geiger2mqtt.ports import PulseCounterPort
from geiger2mqtt.settings import Geiger2MqttSettings

GPIOZERO_ADAPTER = "geiger2mqtt.adapters.gpiozero_adapter:gpiozero_pulse_counter"
"""Import path of the GPIO adapter factory; a string keeps gpiozero unimported."""

type CounterFactory = str | Callable[[Geiger2MqttSettings], PulseCounterPort]


def create_app(
    pulse_counter: CounterFactory = GPIOZERO_ADAPTER,
    dry_run_counter: CounterFactory = fake_pulse_counter,
) -> cosalette.App:
    """Build the app; tests pass their own counter factories."""
    app = cosalette.App(
        name="geiger2mqtt",
        version=__version__,
        description="GPIO geiger counter to MQTT bridge",
        settings_class=Geiger2MqttSettings,
        # Operator opt-in GEIGER2MQTT_MQTT__ERROR_PUBLISH_VERBOSE; off by default.
        allow_error_publish_verbose=True,
        # No exit_after_stale: the radiation channel opts out of freshness
        # below, so nothing could ever trigger it.
        # A GPIO chip that disappears for five health checks re-opens the pin,
        # at most three times before the app gives up and exits.
        restart_after_failures=5,
        max_restarts=3,
        adapters={PulseCounterPort: (pulse_counter, dry_run_counter)},
    )

    # Runtime Home Assistant discovery for the three radiation sensors.
    app.discovery()

    # Publishes on every run, no OnChange: a steady reading is still news.
    app.telemetry(
        "radiation",
        interval=setting_ref("publish_interval"),
        unavailable_on=(NoPulseError,),
        # A dead tube must leave the channel offline and the app running. Every
        # NoPulseError is a failed cycle, so the derived freshness bound would
        # turn the channel stale, and exit_after_stale would then restart the
        # container every few minutes. The handler only reads memory, so
        # staleness has nothing else to detect: a crashed task exits with
        # code 4 and a blocked loop with code 6.
        stale_after=None,
        state_model=RadiationState,
        summary="Counts per minute and dose rates from a GPIO geiger counter",
    )(radiation)

    return app


app = create_app()


def main() -> None:
    """Start the application, or answer a CLI flag such as ``--version``.

    ``cli()`` rather than ``run()``: ``run()`` ignores the command line, so
    ``--help``, ``--version``, ``--dry-run`` and ``--env-file`` would start
    the service instead.
    """
    app.cli()


if __name__ == "__main__":
    main()
