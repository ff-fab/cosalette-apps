"""Typed ``x-cosalette-consumer`` helper shared by the gas2mqtt state models.

The ``GasCounterReading`` and ``TemperatureReading`` payload models both carry
Home Assistant discovery metadata on their fields via
:func:`pydantic.Field`'s ``json_schema_extra``. Building that block through
:func:`_consumer` keeps the two model files consistent with each other (and
with vito2mqtt's ``telemetry_models``) instead of inlining raw
``{"x-cosalette-consumer": {...}}`` dicts, and the :class:`ConsumerMeta`
``TypedDict`` makes call sites fail typecheck if they pass an unknown key.

The metadata rides on the schema through
``TypeAdapter(model).json_schema()``, so it survives
``task gas2mqtt:schema:generate`` with no post-generation hand-application.
"""

from __future__ import annotations

from typing import Any, TypedDict, Unpack


class ConsumerMeta(TypedDict, total=False):
    """Valid Home Assistant discovery keys for ``x-cosalette-consumer``.

    Enumerates every metadata key the gas2mqtt state models forward into MQTT
    discovery — the human-readable ``display_name`` plus the HA sensor
    attributes ``device_class``, ``unit``, ``state_class`` and ``icon``.
    ``total=False`` because each field carries only the subset that applies to
    it.
    """

    display_name: str
    device_class: str
    unit: str
    state_class: str
    icon: str


def _consumer(**metadata: Unpack[ConsumerMeta]) -> dict[str, Any]:
    """Wrap HA-discovery metadata under the ``x-cosalette-consumer`` key.

    Returned dict is passed as ``json_schema_extra`` to
    :func:`pydantic.Field`, so ``TypeAdapter(model).json_schema()`` emits the
    ``x-cosalette-consumer`` block that drives Home Assistant MQTT discovery.
    ``metadata`` is typed via :class:`ConsumerMeta`, so callers are checked
    against the valid discovery keys.
    """

    return {"x-cosalette-consumer": dict(metadata)}
