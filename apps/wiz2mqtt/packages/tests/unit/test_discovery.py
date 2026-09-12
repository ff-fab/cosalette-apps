"""Unit tests for discovery.py — per-bulb HA discovery enrichment .

Mechanism B narrows the advertised ``light`` metadata from a
DeviceStore-cached ``BulbCapabilities``. These tests drive the cache round-trip,
the narrowing rules per bulb class, and the enrich hook, all with an in-memory
store and the fake adapter — no MQTT, no hardware.

Test Techniques Used:
- Specification-based: the narrowed config must match HA's colour-mode contract
- Equivalence Partitioning: RGB / tunable-white / dimmable-white / socket bulb
  classes each map to a distinct advertised colour-mode set
- Boundary Value Analysis: Kelvin range tracks the detected min/max, dropped
  when the bulb has no ``color_temp``
- State Transition: a retyped bulb overwrites its stale cached record
- Error Guessing: uncached bulb, missing store, malformed record, unreachable
  bulb all leave the static superset untouched
- Round-trip Testing: capabilities survive a dict serialise/deserialise cycle
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any

from cosalette import DeviceStore
from cosalette.stores import MemoryStore

from wiz2mqtt.adapters.fake import FakeWizBulbAdapter
from wiz2mqtt.discovery import (
    cache_capabilities,
    capabilities_from_dict,
    capabilities_to_dict,
    load_cached_capabilities,
    make_discovery_enrich,
    narrow_light_discovery,
)
from wiz2mqtt.errors import WizTimeoutError
from wiz2mqtt.models import WIZ_EFFECT_LIST, BulbCapabilities
from wiz2mqtt.settings import BulbConfig

_RGB = BulbCapabilities(
    bulb_class="RGB",
    color=True,
    color_tmp=True,
    effect=True,
    brightness=True,
    kelvin_min=2200,
    kelvin_max=6500,
)
_TW = BulbCapabilities(
    bulb_class="TW",
    color=False,
    color_tmp=True,
    effect=True,
    brightness=True,
    kelvin_min=2700,
    kelvin_max=6500,
)
_DW = BulbCapabilities(
    bulb_class="DW",
    color=False,
    color_tmp=False,
    effect=False,
    brightness=True,
    kelvin_min=None,
    kelvin_max=None,
)
_SOCKET = BulbCapabilities(
    bulb_class="SOCKET",
    color=False,
    color_tmp=False,
    effect=False,
    brightness=False,
    kelvin_min=None,
    kelvin_max=None,
)


def _light_config(name: str = "office", prefix: str = "wiz2mqtt") -> dict[str, Any]:
    """A ``light`` discovery config mirroring ``models._HA_LIGHT_ENTITY``."""
    return {
        "schema": "json",
        "brightness": True,
        "supported_color_modes": ["color_temp", "rgb"],
        "effect": True,
        "effect_list": list(WIZ_EFFECT_LIST),
        "min_kelvin": 2200,
        "max_kelvin": 6500,
        "state_topic": f"{prefix}/{name}/state",
        "command_topic": f"{prefix}/{name}/set",
        "object_id": f"{name}_light",
    }


def _app(store: MemoryStore | None) -> Any:
    """Minimal stand-in exposing only the ``.store`` the enrich hook reads."""
    return SimpleNamespace(store=store)


def _seeded(name: str, caps: BulbCapabilities) -> MemoryStore:
    """A backend pre-populated with *name*'s cached capabilities record."""
    return MemoryStore(initial={name: {"capabilities": capabilities_to_dict(caps)}})


def _loaded_store(backend: MemoryStore, name: str) -> DeviceStore:
    store = DeviceStore(backend, name)
    store.load()
    return store


# --- Capability serialisation ----------------------------------------------


def test_capabilities_dict_round_trips() -> None:
    assert capabilities_from_dict(capabilities_to_dict(_RGB)) == _RGB


def test_load_cached_capabilities_returns_none_when_absent() -> None:
    assert load_cached_capabilities(MemoryStore(), "office") is None


def test_load_cached_capabilities_returns_none_for_malformed_record() -> None:
    backend = MemoryStore(initial={"office": {"capabilities": {"color": True}}})

    assert load_cached_capabilities(backend, "office") is None


def test_load_cached_capabilities_reads_a_valid_record() -> None:
    backend = _seeded("office", _TW)

    assert load_cached_capabilities(backend, "office") == _TW


# --- Narrowing rules --------------------------------------------------------


def test_narrow_rgb_keeps_both_modes_and_detected_kelvin() -> None:
    config = _light_config()

    narrow_light_discovery(config, _RGB)

    assert config["supported_color_modes"] == ["color_temp", "rgb"]
    assert (config["min_kelvin"], config["max_kelvin"]) == (2200, 6500)
    assert config["effect"] is True
    assert config["effect_list"] == list(WIZ_EFFECT_LIST)


def test_narrow_tunable_white_drops_rgb_keeps_kelvin() -> None:
    config = _light_config()

    narrow_light_discovery(config, _TW)

    assert config["supported_color_modes"] == ["color_temp"]
    assert (config["min_kelvin"], config["max_kelvin"]) == (2700, 6500)


def test_narrow_tunable_white_filters_effect_list_by_class() -> None:
    config = _light_config()

    narrow_light_discovery(config, _TW)

    assert config["effect"] is True
    # A TW bulb rejects RGB-only scenes, so they must not be advertised.
    assert "Ocean" not in config["effect_list"]
    # The advertised list stays a subset of the superset, in superset order.
    assert set(config["effect_list"]) < set(WIZ_EFFECT_LIST)
    assert config["effect_list"] == [
        e for e in WIZ_EFFECT_LIST if e in config["effect_list"]
    ]


def test_narrow_dimmable_white_uses_brightness_and_drops_kelvin_and_effects() -> None:
    config = _light_config()

    narrow_light_discovery(config, _DW)

    assert config["supported_color_modes"] == ["brightness"]
    assert "min_kelvin" not in config
    assert "max_kelvin" not in config
    assert config["effect"] is False
    assert "effect_list" not in config


def test_narrow_socket_falls_back_to_onoff() -> None:
    config = _light_config()

    narrow_light_discovery(config, _SOCKET)

    assert config["supported_color_modes"] == ["onoff"]
    assert config["brightness"] is False


def test_narrow_drops_kelvin_when_color_temp_present_but_range_unknown() -> None:
    config = _light_config()

    narrow_light_discovery(config, replace(_TW, kelvin_min=None, kelvin_max=None))

    assert config["supported_color_modes"] == ["color_temp"]
    assert "min_kelvin" not in config


# --- Capability caching -----------------------------------------------------


async def test_cache_capabilities_writes_when_absent() -> None:
    store = _loaded_store(MemoryStore(), "office")
    port = FakeWizBulbAdapter()
    port._capabilities["10.0.0.5"] = _TW

    await cache_capabilities(store, BulbConfig(name="office", ip="10.0.0.5"), port)

    assert store.get("capabilities") == capabilities_to_dict(_TW)
    assert store.dirty


async def test_cache_capabilities_is_noop_when_unchanged() -> None:
    store = _loaded_store(MemoryStore(), "office")
    port = FakeWizBulbAdapter()
    port._capabilities["10.0.0.5"] = _TW
    config = BulbConfig(name="office", ip="10.0.0.5")
    await cache_capabilities(store, config, port)
    store.save()  # clears the dirty flag

    await cache_capabilities(store, config, port)

    assert not store.dirty


async def test_cache_capabilities_updates_on_bulb_retype() -> None:
    backend = _seeded("office", _RGB)
    store = _loaded_store(backend, "office")
    port = FakeWizBulbAdapter()
    port._capabilities["10.0.0.5"] = _TW  # the swapped-in bulb is tunable-white

    await cache_capabilities(store, BulbConfig(name="office", ip="10.0.0.5"), port)

    assert store.get("capabilities") == capabilities_to_dict(_TW)


async def test_cache_capabilities_skips_unreachable_bulb() -> None:
    store = _loaded_store(MemoryStore(), "office")
    port = FakeWizBulbAdapter()
    port._fail_next["10.0.0.5"] = WizTimeoutError("unreachable")

    await cache_capabilities(store, BulbConfig(name="office", ip="10.0.0.5"), port)

    assert "capabilities" not in store


# --- Enrich hook ------------------------------------------------------------


def test_enrich_narrows_a_cached_light() -> None:
    backend = _seeded("office", _TW)
    enrich = make_discovery_enrich(_app(backend))
    config = _light_config("office")

    enrich(None, None, config)  # type: ignore[arg-type]

    assert config["supported_color_modes"] == ["color_temp"]


def test_enrich_leaves_superset_for_uncached_bulb() -> None:
    enrich = make_discovery_enrich(_app(MemoryStore()))
    config = _light_config("office")
    original = dict(config)

    enrich(None, None, config)  # type: ignore[arg-type]

    assert config == original


def test_enrich_ignores_non_light_entity() -> None:
    backend = _seeded("office", _TW)
    enrich = make_discovery_enrich(_app(backend))
    number_config = {
        "object_id": "office_effect_speed",
        "state_topic": "wiz2mqtt/office/state",
        "min": 10,
        "max": 200,
    }
    original = dict(number_config)

    enrich(None, None, number_config)  # type: ignore[arg-type]

    assert number_config == original


def test_enrich_is_noop_without_a_store() -> None:
    enrich = make_discovery_enrich(_app(None))
    config = _light_config("office")
    original = dict(config)

    enrich(None, None, config)  # type: ignore[arg-type]

    assert config == original


def test_enrich_extracts_bulb_name_from_a_prefixed_topic() -> None:
    backend = _seeded("office", _DW)
    enrich = make_discovery_enrich(_app(backend))
    config = _light_config("office", prefix="home/wiz2mqtt")

    enrich(None, None, config)  # type: ignore[arg-type]

    assert config["supported_color_modes"] == ["brightness"]


def test_enrich_leaves_superset_for_malformed_state_topic() -> None:
    backend = _seeded("office", _DW)
    enrich = make_discovery_enrich(_app(backend))
    config = _light_config("office")
    config["state_topic"] = "office/state"  # missing the <prefix> segment
    original = dict(config)

    enrich(None, None, config)  # type: ignore[arg-type]

    assert config == original
