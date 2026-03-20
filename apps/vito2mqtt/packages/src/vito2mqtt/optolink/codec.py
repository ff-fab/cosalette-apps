# Copyright (C) 2026 Fabian Koerner <mail@fabiankoerner.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Data type encoder/decoder for Vitodens 200-W parameters.

Supports 11 type codes actually used by the Vitodens 200-W:

Numeric (language-neutral):
    IS10    — signed fixed-point ÷10
    IUNON   — unsigned integer (no scaling)
    IU3600  — unsigned integer ÷3600 (seconds → hours)
    PR2     — second byte, unsigned
    PR3     — first byte, unsigned ÷2

Enum (language-configurable per ADR-006):
    BA      — Betriebsart (operating mode)
    USV     — Umschaltventil (switch valve)
    ES      — Fehlerspeicher (error history)

Structural (language-neutral):
    RT      — ReturnStatus (IntEnum)
    CT      — CycleTime (timer schedule)
    TI      — SystemTime (BCD-packed datetime)

Public API:
    decode(type_code, data, *, language="en") → decoded value
    encode(type_code, value, *, language="en") → bytes

References:
    ADR-004 — Optolink Protocol Design
    ADR-006 — Configurable Signal Language (DE/EN)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import IntEnum
from typing import Any

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CodecError(Exception):
    """Raised for encoding/decoding failures."""


# ---------------------------------------------------------------------------
# ReturnStatus enum (RT)
# ---------------------------------------------------------------------------


class ReturnStatus(IntEnum):
    """P300 return status codes.

    The boiler returns these in response to read/write operations.
    OFF/ON indicate pump/valve states, UNKNOWN is legacy value 0x03
    (mapped to "2" in pyvcontrol), ERROR signals a failed operation.
    """

    OFF = 0x00
    ON = 0x01
    UNKNOWN = 0x03
    ERROR = 0xAA


# ---------------------------------------------------------------------------
# Enum translation tables (BA, USV, ES) — ADR-006
# ---------------------------------------------------------------------------

_BA_LABELS: dict[str, dict[int, str]] = {
    "de": {
        0x00: "aus",
        0x01: "Red. Betrieb",
        0x02: "Normalbetrieb",
        0x03: "Heizen & WW",
        0x04: "Heizen + WW FS",
        0x05: "Abschaltbetrieb",
    },
    "en": {
        0x00: "off",
        0x01: "reduced",
        0x02: "normal",
        0x03: "heating + dhw",
        0x04: "heating + dhw (ext)",
        0x05: "shutdown",
    },
}

_USV_LABELS: dict[str, dict[int, str]] = {
    "de": {
        0x00: "undefiniert",
        0x01: "Heizen",
        0x02: "Mittelstellung",
        0x03: "Warmwasser",
    },
    "en": {
        0x00: "undefined",
        0x01: "heating",
        0x02: "middle",
        0x03: "hot water",
    },
}

_ES_LABELS: dict[str, dict[int, str]] = {
    "de": {
        0x00: "Regelbetrieb (kein Fehler)",
        0x0F: "Wartung (für Reset Codieradresse 24 auf 0 stellen)",
        0x10: "Kurzschluss Außentemperatursensor",
        0x18: "Unterbrechung Außentemperatursensor",
        0x20: "Kurzschluss Vorlauftemperatursensor",
        0x21: "Kurzschluss Rücklauftemperatursensor",
        0x28: "Unterbrechung Vorlauftemperatursensor",
        0x29: "Unterbrechung Rücklauftemperatursensor",
        0x30: "Kurzschluss Kesseltemperatursensor",
        0x38: "Unterbrechung Kesseltemperatursensor",
        0x40: "Kurzschluss Vorlauftemperatursensor M2",
        0x42: "Unterbrechung Vorlauftemperatursensor M2",
        0x50: "Kurzschluss Speichertemperatursensor",
        0x58: "Unterbrechung Speichertemperatursensor",
        0x92: "Solar: Kurzschluss Kollektortemperatursensor",
        0x93: "Solar: Kurzschluss Sensor S3",
        0x94: "Solar: Kurzschluss Speichertemperatursensor",
        0x9A: "Solar: Unterbrechung Kollektortemperatursensor",
        0x9B: "Solar: Unterbrechung Sensor S3",
        0x9C: "Solar: Unterbrechung Speichertemperatursensor",
        0x9E: (
            "Solar: Zu geringer bzw. kein Volumenstrom oder Temperaturwächter ausgelöst"
        ),
        0x9F: "Solar: Fehlermeldung Solarteil (siehe Solarregler)",
        0xA7: "Bedienteil defekt",
        0xB0: "Kurzschluss Abgastemperatursensor",
        0xB1: "Kommunikationsfehler Bedieneinheit",
        0xB4: "Interner Fehler (Elektronik)",
        0xB5: "Interner Fehler (Elektronik)",
        0xB6: "Ungültige Hardwarekennung (Elektronik)",
        0xB7: "Interner Fehler (Kesselkodierstecker)",
        0xB8: "Unterbrechung Abgastemperatursensor",
        0xB9: "Interner Fehler (Dateneingabe wiederholen)",
        0xBA: "Kommunikationsfehler Erweiterungssatz für Mischerkreis M2",
        0xBC: "Kommunikationsfehler Fernbedienung Vitorol, Heizkreis M1",
        0xBD: "Kommunikationsfehler Fernbedienung Vitorol, Heizkreis M2",
        0xBE: "Falsche Codierung Fernbedienung Vitorol",
        0xC1: "Externe Sicherheitseinrichtung (Kessel kühlt aus)",
        0xC2: "Kommunikationsfehler Solarregelung",
        0xC5: "Kommunikationsfehler drehzahlgeregelte Heizkreispumpe, Heizkreis M1",
        0xC6: "Kommunikationsfehler drehzahlgeregelte Heizkreispumpe, Heizkreis M2",
        0xC7: "Falsche Codierung der Heizkreispumpe",
        0xC9: "Störmeldeeingang am Schaltmodul-V aktiv",
        0xCD: "Kommunikationsfehler Vitocom 100 (KM-BUS)",
        0xCE: "Kommunikationsfehler Schaltmodul-V",
        0xCF: "Kommunikationsfehler LON Modul",
        0xD1: "Brennerstörung",
        0xD4: (
            "Sicherheitstemperaturbegrenzer hat ausgelöst"
            " oder Störmeldemodul nicht richtig gesteckt"
        ),
        0xDA: "Kurzschluss Raumtemperatursensor, Heizkreis M1",
        0xDB: "Kurzschluss Raumtemperatursensor, Heizkreis M2",
        0xDD: "Unterbrechung Raumtemperatursensor, Heizkreis M1",
        0xDE: "Unterbrechung Raumtemperatursensor, Heizkreis M2",
        0xE4: "Fehler Versorgungsspannung",
        0xE5: "Interner Fehler (Ionisationselektrode)",
        0xE6: "Abgas-/Zuluftsystem verstopft",
        0xF0: "Interner Fehler (Regelung tauschen)",
        0xF1: "Abgastemperaturbegrenzer ausgelöst",
        0xF2: "Temperaturbegrenzer ausgelöst",
        0xF3: "Flammensignal beim Brennerstart bereits vorhanden",
        0xF4: "Flammensignal nicht vorhanden",
        0xF7: "Differenzdrucksensor defekt",
        0xF8: "Brennstoffventil schließt zu spät",
        0xF9: "Gebläsedrehzahl beim Brennerstart zu niedrig",
        0xFA: "Gebläsestillstand nicht erreicht",
        0xFD: "Fehler Gasfeuerungsautomat",
        0xFE: "Starkes Störfeld (EMV) in der Nähe oder Elektronik defekt",
        0xFF: "Starkes Störfeld (EMV) in der Nähe oder interner Fehler",
    },
    "en": {
        0x00: "normal operation (no error)",
        0x0F: "maintenance (reset coding address 24 to 0)",
        0x10: "short circuit outdoor temperature sensor",
        0x18: "open circuit outdoor temperature sensor",
        0x20: "short circuit flow temperature sensor",
        0x21: "short circuit return temperature sensor",
        0x28: "open circuit flow temperature sensor",
        0x29: "open circuit return temperature sensor",
        0x30: "short circuit boiler temperature sensor",
        0x38: "open circuit boiler temperature sensor",
        0x40: "short circuit flow temperature sensor M2",
        0x42: "open circuit flow temperature sensor M2",
        0x50: "short circuit storage temperature sensor",
        0x58: "open circuit storage temperature sensor",
        0x92: "solar: short circuit collector temp sensor",
        0x93: "solar: short circuit sensor S3",
        0x94: "solar: short circuit storage temp sensor",
        0x9A: "solar: open circuit collector temp sensor",
        0x9B: "solar: open circuit sensor S3",
        0x9C: "solar: open circuit storage temp sensor",
        0x9E: "solar: insufficient flow rate or thermal cutout triggered",
        0x9F: "solar: error in solar module (see controller)",
        0xA7: "control panel defective",
        0xB0: "short circuit exhaust temperature sensor",
        0xB1: "communication error control unit",
        0xB4: "internal error (electronics)",
        0xB5: "internal error (electronics)",
        0xB6: "invalid hardware ID (electronics)",
        0xB7: "internal error (boiler coding plug)",
        0xB8: "open circuit exhaust temperature sensor",
        0xB9: "internal error (repeat data entry)",
        0xBA: "communication error mixer circuit M2 ext",
        0xBC: "communication error remote control Vitorol, heating circuit M1",
        0xBD: "communication error remote control Vitorol, heating circuit M2",
        0xBE: "incorrect coding remote control Vitorol",
        0xC1: "external safety device (boiler cooling down)",
        0xC2: "communication error solar controller",
        0xC5: "communication error variable-speed pump, heating circuit M1",
        0xC6: "communication error variable-speed pump, heating circuit M2",
        0xC7: "incorrect coding heating circuit pump",
        0xC9: "fault input at switching module V active",
        0xCD: "communication error Vitocom 100 (KM-BUS)",
        0xCE: "communication error switching module V",
        0xCF: "communication error LON module",
        0xD1: "burner fault",
        0xD4: (
            "safety temperature limiter triggered or fault module not seated correctly"
        ),
        0xDA: "short circuit room temperature sensor, heating circuit M1",
        0xDB: "short circuit room temperature sensor, heating circuit M2",
        0xDD: "open circuit room temperature sensor, heating circuit M1",
        0xDE: "open circuit room temperature sensor, heating circuit M2",
        0xE4: "supply voltage error",
        0xE5: "internal error (ionisation electrode)",
        0xE6: "exhaust/intake system blocked",
        0xF0: "internal error (replace controller)",
        0xF1: "exhaust temperature limiter triggered",
        0xF2: "temperature limiter triggered",
        0xF3: "flame signal present at burner start",
        0xF4: "flame signal not present",
        0xF7: "differential pressure sensor defective",
        0xF8: "fuel valve closing too late",
        0xF9: "fan speed too low at burner start",
        0xFA: "fan standstill not reached",
        0xFD: "gas burner control error",
        0xFE: "strong interference field (EMC) or electronics defective",
        0xFF: "strong interference field (EMC) or internal error",
    },
}

# Reverse maps for encoding (label → byte value)
_BA_REVERSE: dict[str, dict[str, int]] = {
    lang: {label: code for code, label in table.items()}
    for lang, table in _BA_LABELS.items()
}
_USV_REVERSE: dict[str, dict[str, int]] = {
    lang: {label: code for code, label in table.items()}
    for lang, table in _USV_LABELS.items()
}


# ---------------------------------------------------------------------------
# CycleTime type aliases
# ---------------------------------------------------------------------------

# A single time slot: [hours, minutes] where None means "not set"
TimeSlot = list[int | None]
# A cycle time pair: [start, stop]
CycleTimePair = list[TimeSlot]
# Full cycle time: list of 4 pairs (8 bytes)
CycleTimeSchedule = list[CycleTimePair]

# Sentinel values for "not set" in cycle time bytes
_CT_HOURS_UNSET = 31
_CT_MINUTES_UNSET = 70


# ---------------------------------------------------------------------------
# Decode functions
# ---------------------------------------------------------------------------


def _decode_is10(data: bytes) -> float:
    """IS10: signed fixed-point integer ÷ 10."""
    return int.from_bytes(data, "little", signed=True) / 10


def _decode_iunon(data: bytes) -> int:
    """IUNON: unsigned integer, no scaling."""
    return int.from_bytes(data, "little", signed=False)


def _decode_iu3600(data: bytes) -> float:
    """IU3600: unsigned integer ÷ 3600 (seconds → hours)."""
    return int.from_bytes(data, "little", signed=False) / 3600


def _decode_pr2(data: bytes) -> int:
    """PR2: second byte as unsigned integer."""
    if len(data) < 2:  # noqa: PLR2004
        raise CodecError(f"PR2 requires at least 2 bytes, got {len(data)}")
    return data[1]


def _decode_pr3(data: bytes) -> float:
    """PR3: first byte as unsigned integer ÷ 2."""
    return data[0] / 2


def _decode_ba(data: bytes, language: str) -> str:
    """BA: operating mode enum → label."""
    code = int.from_bytes(data, "little")
    labels = _BA_LABELS.get(language, _BA_LABELS["en"])
    if code not in labels:
        raise CodecError(f"Unknown BA operating mode: 0x{code:02X}")
    return labels[code]


def _decode_usv(data: bytes, language: str) -> str:
    """USV: switch valve state enum → label."""
    code = int.from_bytes(data, "little")
    labels = _USV_LABELS.get(language, _USV_LABELS["en"])
    if code not in labels:
        raise CodecError(f"Unknown USV switch valve state: 0x{code:02X}")
    return labels[code]


def _decode_es(data: bytes, language: str) -> list[Any]:
    """ES: error code + BCD timestamp → [label, datetime].

    The ES data is 9 bytes: 1 byte error code + 8 bytes BCD timestamp.
    """
    if len(data) < 9:  # noqa: PLR2004
        raise CodecError(f"ES requires 9 bytes, got {len(data)}")
    error_code = data[0]
    labels = _ES_LABELS.get(language, _ES_LABELS["en"])
    if error_code not in labels:
        raise CodecError(f"Unknown ES error code: 0x{error_code:02X}")
    label = labels[error_code]
    timestamp = _decode_bcd_datetime(data[1:9])
    return [label, timestamp]


def _decode_rt(data: bytes) -> ReturnStatus:
    """RT: return status byte → ReturnStatus enum."""
    code = data[0]
    try:
        return ReturnStatus(code)
    except ValueError:
        raise CodecError(f"Unknown RT return status: 0x{code:02X}") from None


def _decode_ct(data: bytes) -> CycleTimeSchedule:
    """CT: cycle time schedule (8 bytes → 4 start/stop pairs)."""
    if len(data) < 8:  # noqa: PLR2004
        raise CodecError(f"CT requires 8 bytes, got {len(data)}")
    result: CycleTimeSchedule = []
    for i in range(4):
        start_byte = data[i * 2]
        stop_byte = data[i * 2 + 1]
        start = _decode_ct_byte(start_byte)
        stop = _decode_ct_byte(stop_byte)
        result.append([start, stop])
    return result


def _decode_ct_byte(byte: int) -> TimeSlot:
    """Decode a single CT byte into [hours, minutes]."""
    hours = byte >> 3
    minutes = (byte & 0x07) * 10
    return [
        None if hours == _CT_HOURS_UNSET else hours,
        None if minutes == _CT_MINUTES_UNSET else minutes,
    ]


def _decode_ti(data: bytes) -> datetime:
    """TI: system time (8 bytes BCD-packed → datetime)."""
    if len(data) < 8:  # noqa: PLR2004
        raise CodecError(f"TI requires 8 bytes, got {len(data)}")
    return _decode_bcd_datetime(data[:8])


def _decode_bcd_datetime(data: bytes) -> datetime:
    """Decode 8 BCD bytes into a datetime.

    Byte layout: [year_hi, year_lo, month, day, weekday,
                  hour, minute, second]

    Each byte is BCD-encoded: 0x20 means decimal 20, 0x06 means 6.

    Raises:
        CodecError: If any byte contains non-BCD nibbles or the
            resulting date/time is invalid.
    """
    try:
        year = int(f"{data[0]:02X}{data[1]:02X}")
        month = int(f"{data[2]:02X}")
        day = int(f"{data[3]:02X}")
        # data[4] is weekday — not used in datetime
        hour = int(f"{data[5]:02X}")
        minute = int(f"{data[6]:02X}")
        second = int(f"{data[7]:02X}")
        return datetime(year, month, day, hour, minute, second)
    except (ValueError, OverflowError) as exc:
        raise CodecError(f"Invalid BCD datetime: {exc}") from exc


# ---------------------------------------------------------------------------
# Encode functions
# ---------------------------------------------------------------------------


def _encode_is10(value: float, byte_length: int = 2) -> bytes:
    """IS10: float → signed fixed-point × 10."""
    raw = int(value * 10)
    return raw.to_bytes(byte_length, "little", signed=True)


def _encode_iunon(value: int, byte_length: int = 2) -> bytes:
    """IUNON: int → unsigned bytes."""
    return value.to_bytes(byte_length, "little", signed=False)


def _encode_iu3600(value: float, byte_length: int = 2) -> bytes:
    """IU3600: float (hours) → unsigned integer × 3600."""
    raw = int(value * 3600)
    return raw.to_bytes(byte_length, "little", signed=False)


def _encode_ba(value: str, language: str) -> bytes:
    """BA: label → operating mode byte."""
    # Try the specified language first, fall back to checking all
    reverse = _BA_REVERSE.get(language, _BA_REVERSE["en"])
    if value in reverse:
        return reverse[value].to_bytes(1, "little")
    # Try all languages as fallback for interoperability
    for lang_reverse in _BA_REVERSE.values():
        if value in lang_reverse:
            return lang_reverse[value].to_bytes(1, "little")
    valid = list(reverse.keys())
    raise CodecError(f"Unknown BA label: {value!r}. Valid ({language}): {valid}")


def _encode_usv(value: str, language: str) -> bytes:
    """USV: label → switch valve state byte."""
    reverse = _USV_REVERSE.get(language, _USV_REVERSE["en"])
    if value in reverse:
        return reverse[value].to_bytes(1, "little")
    for lang_reverse in _USV_REVERSE.values():
        if value in lang_reverse:
            return lang_reverse[value].to_bytes(1, "little")
    valid = list(reverse.keys())
    raise CodecError(f"Unknown USV label: {value!r}. Valid ({language}): {valid}")


def _encode_ct(schedule: CycleTimeSchedule) -> bytes:
    """CT: cycle time schedule → 8 bytes."""
    result = bytearray()
    for pair in schedule:
        for slot in pair:
            hours = slot[0] if slot[0] is not None else _CT_HOURS_UNSET
            minutes = slot[1] if slot[1] is not None else _CT_MINUTES_UNSET
            byte = (hours << 3) + (minutes // 10)
            result.append(byte)
    return bytes(result)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Type codes that require language parameter
_ENUM_TYPES = frozenset({"BA", "USV", "ES"})

# Supported type codes
_ALL_TYPES = frozenset(
    {
        "IS10",
        "IUNON",
        "IU3600",
        "PR2",
        "PR3",
        "BA",
        "USV",
        "ES",
        "RT",
        "CT",
        "TI",
    }
)

# Dispatch tables — one entry per type code
# Decoders without language parameter: bytes → value
_DECODE_SIMPLE: dict[str, Callable[[bytes], Any]] = {
    "IS10": _decode_is10,
    "IUNON": _decode_iunon,
    "IU3600": _decode_iu3600,
    "PR2": _decode_pr2,
    "PR3": _decode_pr3,
    "RT": _decode_rt,
    "CT": _decode_ct,
    "TI": _decode_ti,
}

# Decoders that accept a language parameter: (bytes, str) → value
_DECODE_LANG: dict[str, Callable[[bytes, str], Any]] = {
    "BA": _decode_ba,
    "USV": _decode_usv,
    "ES": _decode_es,
}

# Encoders: numeric (value, byte_length), language (value, language), plain (value,)
_ENCODE_NUMERIC: dict[str, Callable[[Any, int], bytes]] = {
    "IS10": _encode_is10,
    "IUNON": _encode_iunon,
    "IU3600": _encode_iu3600,
}
_ENCODE_LANG: dict[str, Callable[[Any, str], bytes]] = {
    "BA": _encode_ba,
    "USV": _encode_usv,
}
_ENCODE_PLAIN: dict[str, Callable[[Any], bytes]] = {
    "CT": _encode_ct,
}
_ENCODE_UNSUPPORTED = frozenset({"PR2", "PR3", "RT", "ES", "TI"})


def decode(
    type_code: str,
    data: bytes,
    *,
    language: str = "en",
) -> Any:
    """Decode raw bytes into a typed value.

    Args:
        type_code: One of the 11 supported type codes.
        data: Raw bytes from the boiler response payload.
        language: Language for enum-type values (``"de"`` or ``"en"``).
            Only affects BA, USV, and ES codecs. Default ``"en"``.

    Returns:
        Decoded value — type depends on the codec:
        - IS10, IU3600, PR3: ``float``
        - IUNON, PR2: ``int``
        - BA, USV: ``str``
        - ES: ``list[str, datetime]``
        - RT: ``ReturnStatus``
        - CT: ``CycleTimeSchedule``
        - TI: ``datetime``

    Raises:
        CodecError: If type_code is unknown or data is malformed.
    """
    if type_code not in _ALL_TYPES:
        raise CodecError(f"Unknown type code: {type_code!r}")

    if type_code in _DECODE_LANG:
        return _DECODE_LANG[type_code](data, language)
    return _DECODE_SIMPLE[type_code](data)


def encode(
    type_code: str,
    value: Any,
    *,
    language: str = "en",
    byte_length: int = 2,
) -> bytes:
    """Encode a typed value into raw bytes for a write request.

    Args:
        type_code: One of the writable type codes.
        value: The typed value to encode.
        language: Language for enum-type labels. Default ``"en"``.
        byte_length: Target byte length for numeric types.

    Returns:
        Encoded bytes suitable for a P300 write payload.

    Raises:
        CodecError: If type_code is unknown, value is invalid,
            or encoding is not supported for the type.
    """
    if type_code not in _ALL_TYPES:
        raise CodecError(f"Unknown type code: {type_code!r}")

    if type_code in _ENCODE_UNSUPPORTED:
        raise CodecError(f"Encoding not supported for type {type_code!r}")
    if type_code in _ENCODE_NUMERIC:
        return _ENCODE_NUMERIC[type_code](value, byte_length)
    if type_code in _ENCODE_LANG:
        return _ENCODE_LANG[type_code](value, language)
    return _ENCODE_PLAIN[type_code](value)
