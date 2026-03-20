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

"""Unit tests for optolink/codec.py — Data type encoder/decoder.

Test Techniques Used:
- Specification-based: Verify codec behavior against P300 data type specs
- Round-trip Testing: encode → decode fidelity for writable types
- Equivalence Partitioning: Each type code, each language, each enum value
- Boundary Value Analysis: Min/max values, zero, negative, overflow
- Error Guessing: Unknown codes, malformed data, unsupported encode
- Decision Table: Language parameter × type code → expected behavior
"""

from __future__ import annotations

from datetime import datetime

import pytest

from vito2mqtt.optolink.codec import (
    CodecError,
    ReturnStatus,
    decode,
    encode,
)

# ---------------------------------------------------------------------------
# IS10 — Signed fixed-point ÷ 10
# ---------------------------------------------------------------------------


class TestIS10:
    """IS10: 2-byte signed integer divided by 10.

    Used for temperatures (e.g., 23.9°C = 0x00EF = 239 → 23.9).
    """

    def test_decode_positive_temperature(self) -> None:
        """0x00EF (239) → 23.9°C.

        Technique: Specification-based — known protocol example.
        """
        assert decode("IS10", b"\xef\x00") == pytest.approx(23.9)

    def test_decode_negative_temperature(self) -> None:
        """Negative value: -5.0°C = -50 as signed LE = 0xFFCE.

        Technique: Equivalence Partitioning — negative value class.
        """
        raw = (-50).to_bytes(2, "little", signed=True)
        assert decode("IS10", raw) == pytest.approx(-5.0)

    def test_decode_zero(self) -> None:
        """0x0000 → 0.0.

        Technique: Boundary Value Analysis — zero.
        """
        assert decode("IS10", b"\x00\x00") == pytest.approx(0.0)

    def test_decode_max_positive(self) -> None:
        """0x7FFF (32767) → 3276.7.

        Technique: Boundary Value Analysis — max signed 16-bit.
        """
        assert decode("IS10", b"\xff\x7f") == pytest.approx(3276.7)

    def test_decode_max_negative(self) -> None:
        """0x8000 (-32768) → -3276.8.

        Technique: Boundary Value Analysis — min signed 16-bit.
        """
        assert decode("IS10", b"\x00\x80") == pytest.approx(-3276.8)

    def test_encode_positive(self) -> None:
        """23.9 → 0xEF00 (LE).

        Technique: Round-trip Testing.
        """
        assert encode("IS10", 23.9) == b"\xef\x00"

    def test_encode_negative(self) -> None:
        """-5.0 → signed LE bytes.

        Technique: Round-trip Testing.
        """
        result = encode("IS10", -5.0)
        assert decode("IS10", result) == pytest.approx(-5.0)

    def test_roundtrip(self) -> None:
        """Encode then decode preserves value.

        Technique: Round-trip Testing.
        """
        for value in [0.0, 10.5, -10.5, 100.0, -60.0]:
            encoded = encode("IS10", value)
            assert decode("IS10", encoded) == pytest.approx(value)

    def test_language_ignored(self) -> None:
        """Language parameter has no effect on numeric types.

        Technique: Decision Table — numeric × language.
        """
        assert decode("IS10", b"\xef\x00", language="de") == pytest.approx(23.9)


# ---------------------------------------------------------------------------
# IUNON — Unsigned integer, no scaling
# ---------------------------------------------------------------------------


class TestIUNON:
    """IUNON: unsigned integer, no scaling.

    Used for counts, statuses, and raw values.
    """

    def test_decode_two_bytes(self) -> None:
        """0x03E8 = 1000 (LE: E8 03).

        Technique: Specification-based.
        """
        assert decode("IUNON", b"\xe8\x03") == 1000

    def test_decode_zero(self) -> None:
        """Technique: Boundary Value Analysis — zero."""
        assert decode("IUNON", b"\x00\x00") == 0

    def test_decode_max_16bit(self) -> None:
        """0xFFFF = 65535.

        Technique: Boundary Value Analysis — max unsigned 16-bit.
        """
        assert decode("IUNON", b"\xff\xff") == 65535

    def test_decode_four_bytes(self) -> None:
        """4-byte unsigned for burner hours etc.

        Technique: Equivalence Partitioning — 4-byte variant.
        """
        # 100000 = 0x000186A0, LE: A0 86 01 00
        assert decode("IUNON", b"\xa0\x86\x01\x00") == 100000

    def test_encode_two_bytes(self) -> None:
        """Technique: Round-trip Testing."""
        assert encode("IUNON", 1000) == b"\xe8\x03"

    def test_roundtrip(self) -> None:
        """Technique: Round-trip Testing."""
        for value in [0, 1, 255, 1000, 65535]:
            assert decode("IUNON", encode("IUNON", value)) == value


# ---------------------------------------------------------------------------
# IU3600 — Unsigned integer ÷ 3600
# ---------------------------------------------------------------------------


class TestIU3600:
    """IU3600: unsigned integer ÷ 3600 (seconds → hours).

    Used for burner hours.
    """

    def test_decode_one_hour(self) -> None:
        """3600 seconds → 1.0 hours.

        Technique: Specification-based.
        """
        raw = (3600).to_bytes(2, "little", signed=False)
        assert decode("IU3600", raw) == pytest.approx(1.0)

    def test_decode_zero(self) -> None:
        """Technique: Boundary Value Analysis — zero."""
        assert decode("IU3600", b"\x00\x00") == pytest.approx(0.0)

    def test_encode_one_hour(self) -> None:
        """1.0 hours → 3600 as unsigned LE.

        Technique: Round-trip Testing.
        """
        result = encode("IU3600", 1.0)
        assert decode("IU3600", result) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# PR2 — Second byte, unsigned
# ---------------------------------------------------------------------------


class TestPR2:
    """PR2: extract second byte as unsigned integer.

    Used for pump modulation level (byte index 1 of 2-byte data).
    """

    def test_decode_second_byte(self) -> None:
        """Data [0x10, 0x42] → 0x42 = 66.

        Technique: Specification-based.
        """
        assert decode("PR2", b"\x10\x42") == 66

    def test_decode_zero_first_byte(self) -> None:
        """First byte irrelevant, second byte is value.

        Technique: Equivalence Partitioning.
        """
        assert decode("PR2", b"\xff\x00") == 0

    def test_decode_too_short_raises(self) -> None:
        """PR2 needs at least 2 bytes.

        Technique: Boundary Value Analysis — below minimum.
        """
        with pytest.raises(CodecError, match="2 bytes"):
            decode("PR2", b"\x42")

    def test_encode_not_supported(self) -> None:
        """PR2 is read-only.

        Technique: Error Guessing — unsupported encode.
        """
        with pytest.raises(CodecError, match="not supported"):
            encode("PR2", 42)


# ---------------------------------------------------------------------------
# PR3 — First byte ÷ 2
# ---------------------------------------------------------------------------


class TestPR3:
    """PR3: first byte as unsigned integer ÷ 2.

    Used for pump power percentage.
    """

    def test_decode_first_byte(self) -> None:
        """Data [0x50, 0x00] → 0x50/2 = 40.0.

        Technique: Specification-based.
        """
        assert decode("PR3", b"\x50\x00") == pytest.approx(40.0)

    def test_decode_odd_value(self) -> None:
        """Odd bytes produce .5 fractions.

        Technique: Equivalence Partitioning.
        """
        assert decode("PR3", b"\x03\x00") == pytest.approx(1.5)

    def test_encode_not_supported(self) -> None:
        """PR3 is read-only.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="not supported"):
            encode("PR3", 40.0)


# ---------------------------------------------------------------------------
# BA — Operating mode (Betriebsart) — language-configurable
# ---------------------------------------------------------------------------


class TestBA:
    """BA: operating mode with DE/EN language support.

    Technique: Decision Table — code × language → label.
    """

    @pytest.mark.parametrize(
        ("code", "expected_en"),
        [
            (0x00, "off"),
            (0x01, "reduced"),
            (0x02, "normal"),
            (0x03, "heating + dhw"),
            (0x04, "heating + dhw (ext)"),
            (0x05, "shutdown"),
        ],
        ids=[
            "off",
            "reduced",
            "normal",
            "heating+dhw",
            "heating+dhw-ext",
            "shutdown",
        ],
    )
    def test_decode_all_modes_en(self, code: int, expected_en: str) -> None:
        """All 6 BA modes decode correctly in English."""
        assert decode("BA", bytes([code]), language="en") == expected_en

    @pytest.mark.parametrize(
        ("code", "expected_de"),
        [
            (0x00, "aus"),
            (0x01, "Red. Betrieb"),
            (0x02, "Normalbetrieb"),
            (0x03, "Heizen & WW"),
            (0x04, "Heizen + WW FS"),
            (0x05, "Abschaltbetrieb"),
        ],
        ids=[
            "aus",
            "Red-Betrieb",
            "Normalbetrieb",
            "Heizen-WW",
            "Heizen-WW-FS",
            "Abschaltbetrieb",
        ],
    )
    def test_decode_all_modes_de(self, code: int, expected_de: str) -> None:
        """All 6 BA modes decode correctly in German."""
        assert decode("BA", bytes([code]), language="de") == expected_de

    def test_decode_default_language_is_english(self) -> None:
        """Without language param, default is English.

        Technique: Specification-based — ADR-006 default.
        """
        assert decode("BA", b"\x02") == "normal"

    def test_decode_unknown_code_raises(self) -> None:
        """Unknown BA code raises CodecError.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="Unknown BA"):
            decode("BA", b"\xff")

    def test_encode_en_label(self) -> None:
        """Encode English label to byte.

        Technique: Round-trip Testing.
        """
        assert encode("BA", "normal", language="en") == b"\x02"

    def test_encode_de_label(self) -> None:
        """Encode German label to byte.

        Technique: Round-trip Testing.
        """
        assert encode("BA", "Normalbetrieb", language="de") == b"\x02"

    def test_encode_cross_language_fallback(self) -> None:
        """Encoding a DE label while language='en' still works.

        The encoder tries the specified language first, then falls back
        to checking all languages for interoperability.

        Technique: Error Guessing — cross-language write.
        """
        assert encode("BA", "Normalbetrieb", language="en") == b"\x02"

    def test_encode_unknown_label_raises(self) -> None:
        """Unknown label raises CodecError.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="Unknown BA"):
            encode("BA", "nonexistent")

    def test_roundtrip_all_modes(self) -> None:
        """Round-trip all BA modes through encode → decode.

        Technique: Round-trip Testing — exhaustive.
        """
        for lang in ("en", "de"):
            for code in range(6):
                label = decode("BA", bytes([code]), language=lang)
                encoded = encode("BA", label, language=lang)
                assert encoded == bytes([code])


# ---------------------------------------------------------------------------
# USV — Switch valve (Umschaltventil) — language-configurable
# ---------------------------------------------------------------------------


class TestUSV:
    """USV: three-way switch valve with DE/EN language support."""

    @pytest.mark.parametrize(
        ("code", "expected_en"),
        [
            (0x00, "undefined"),
            (0x01, "heating"),
            (0x02, "middle"),
            (0x03, "hot water"),
        ],
        ids=["undefined", "heating", "middle", "hot-water"],
    )
    def test_decode_all_states_en(self, code: int, expected_en: str) -> None:
        """All 4 USV states decode correctly in English."""
        assert decode("USV", bytes([code]), language="en") == expected_en

    @pytest.mark.parametrize(
        ("code", "expected_de"),
        [
            (0x00, "undefiniert"),
            (0x01, "Heizen"),
            (0x02, "Mittelstellung"),
            (0x03, "Warmwasser"),
        ],
        ids=["undefiniert", "Heizen", "Mittelstellung", "Warmwasser"],
    )
    def test_decode_all_states_de(self, code: int, expected_de: str) -> None:
        """All 4 USV states decode correctly in German."""
        assert decode("USV", bytes([code]), language="de") == expected_de

    def test_decode_default_is_english(self) -> None:
        """Technique: Specification-based — ADR-006 default."""
        assert decode("USV", b"\x03") == "hot water"

    def test_decode_unknown_raises(self) -> None:
        """Technique: Error Guessing."""
        with pytest.raises(CodecError, match="Unknown USV"):
            decode("USV", b"\xff")

    def test_encode_roundtrip(self) -> None:
        """Technique: Round-trip Testing."""
        for lang in ("en", "de"):
            for code in range(4):
                label = decode("USV", bytes([code]), language=lang)
                encoded = encode("USV", label, language=lang)
                assert encoded == bytes([code])


# ---------------------------------------------------------------------------
# ES — Error codes (Fehlerspeicher) — language-configurable
# ---------------------------------------------------------------------------


class TestES:
    """ES: error code + BCD timestamp, with DE/EN labels."""

    def _make_es_data(self, error_code: int) -> bytes:
        """Build 9-byte ES data: 1 byte code + 8 bytes BCD timestamp.

        Timestamp: 2026-02-28 14:30:00 (a known date for tests).
        """
        return bytes(
            [
                error_code,
                0x20,
                0x26,  # year 2026
                0x02,  # month 02
                0x28,  # day 28
                0x06,  # weekday (Saturday)
                0x14,  # hour 14
                0x30,  # minute 30
                0x00,  # second 00
            ]
        )

    def test_decode_no_error_en(self) -> None:
        """Error code 0x00 → 'normal operation (no error)'.

        Technique: Specification-based.
        """
        result = decode("ES", self._make_es_data(0x00), language="en")
        assert result[0] == "normal operation (no error)"
        assert isinstance(result[1], datetime)

    def test_decode_no_error_de(self) -> None:
        """Error code 0x00 → 'Regelbetrieb (kein Fehler)'.

        Technique: Specification-based.
        """
        result = decode("ES", self._make_es_data(0x00), language="de")
        assert result[0] == "Regelbetrieb (kein Fehler)"

    def test_decode_burner_fault_en(self) -> None:
        """Error code 0xD1 → 'burner fault'.

        Technique: Equivalence Partitioning — specific error.
        """
        result = decode("ES", self._make_es_data(0xD1), language="en")
        assert result[0] == "burner fault"

    def test_decode_burner_fault_de(self) -> None:
        """Error code 0xD1 → 'Brennerstörung'.

        Technique: Equivalence Partitioning — DE variant.
        """
        result = decode("ES", self._make_es_data(0xD1), language="de")
        assert result[0] == "Brennerstörung"

    def test_decode_timestamp_parsed(self) -> None:
        """BCD timestamp is correctly parsed.

        Technique: Specification-based — BCD datetime format.
        """
        result = decode("ES", self._make_es_data(0x00), language="en")
        assert result[1] == datetime(2026, 2, 28, 14, 30, 0)

    def test_decode_unknown_error_code_raises(self) -> None:
        """Unknown error code raises CodecError.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="Unknown ES"):
            decode("ES", self._make_es_data(0x01))

    def test_decode_too_short_raises(self) -> None:
        """ES requires 9 bytes (code + 8 timestamp).

        Technique: Boundary Value Analysis.
        """
        with pytest.raises(CodecError, match="9 bytes"):
            decode("ES", b"\x00\x20\x26")

    def test_decode_default_language_is_english(self) -> None:
        """Technique: Specification-based — ADR-006 default."""
        result = decode("ES", self._make_es_data(0x00))
        assert result[0] == "normal operation (no error)"

    def test_encode_not_supported(self) -> None:
        """ES is read-only (errors come from the boiler).

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="not supported"):
            encode("ES", "burner fault")

    def test_all_error_codes_have_both_languages(self) -> None:
        """Every DE error code has an EN equivalent and vice versa.

        Technique: Specification-based — translation table completeness.
        """
        from vito2mqtt.optolink.codec import _ES_LABELS

        assert set(_ES_LABELS["de"].keys()) == set(_ES_LABELS["en"].keys())


# ---------------------------------------------------------------------------
# RT — ReturnStatus (IntEnum)
# ---------------------------------------------------------------------------


class TestRT:
    """RT: return status as IntEnum."""

    def test_decode_off(self) -> None:
        """0x00 → ReturnStatus.OFF.

        Technique: Specification-based.
        """
        assert decode("RT", b"\x00") is ReturnStatus.OFF

    def test_decode_on(self) -> None:
        """0x01 → ReturnStatus.ON.

        Technique: Specification-based.
        """
        assert decode("RT", b"\x01") is ReturnStatus.ON

    def test_decode_unknown(self) -> None:
        """0x03 → ReturnStatus.UNKNOWN (legacy '2' value).

        Technique: Specification-based — legacy mapping.
        """
        assert decode("RT", b"\x03") is ReturnStatus.UNKNOWN

    def test_decode_error(self) -> None:
        """0xAA → ReturnStatus.ERROR (legacy 'Not OK').

        Technique: Specification-based — error detection.
        """
        assert decode("RT", b"\xaa") is ReturnStatus.ERROR

    def test_decode_invalid_raises(self) -> None:
        """Unknown RT code raises CodecError.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="Unknown RT"):
            decode("RT", b"\x42")

    def test_return_status_values(self) -> None:
        """IntEnum values match protocol spec.

        Technique: Specification-based — enum constants.
        """
        assert ReturnStatus.OFF == 0x00
        assert ReturnStatus.ON == 0x01
        assert ReturnStatus.UNKNOWN == 0x03
        assert ReturnStatus.ERROR == 0xAA

    def test_language_ignored(self) -> None:
        """Language has no effect on RT.

        Technique: Decision Table — structural × language.
        """
        assert decode("RT", b"\x01", language="de") is ReturnStatus.ON

    def test_encode_not_supported(self) -> None:
        """RT is read-only.

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="not supported"):
            encode("RT", ReturnStatus.ON)


# ---------------------------------------------------------------------------
# CT — CycleTime (timer schedule)
# ---------------------------------------------------------------------------


class TestCT:
    """CT: cycle time schedule (4 start/stop pairs in 8 bytes)."""

    def test_decode_simple_schedule(self) -> None:
        """One active pair: 06:00–22:00, rest unset.

        Byte encoding: hours << 3 + minutes // 10
        06:00 = (6 << 3) + 0 = 48 = 0x30
        22:00 = (22 << 3) + 0 = 176 = 0xB0
        Unset: (31 << 3) + 7 = 255 = 0xFF

        Technique: Specification-based.
        """
        data = bytes([0x30, 0xB0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
        result = decode("CT", data)

        assert result[0] == [[6, 0], [22, 0]]
        assert result[1] == [[None, None], [None, None]]
        assert result[2] == [[None, None], [None, None]]
        assert result[3] == [[None, None], [None, None]]

    def test_decode_two_pairs(self) -> None:
        """Two active pairs with 10-minute granularity.

        Technique: Equivalence Partitioning — multiple pairs.
        """
        # 10:20 = (10 << 3) + 2 = 82 = 0x52
        # 12:30 = (12 << 3) + 3 = 99 = 0x63
        # 14:00 = (14 << 3) + 0 = 112 = 0x70
        # 18:50 = (18 << 3) + 5 = 149 = 0x95
        data = bytes([0x52, 0x63, 0x70, 0x95, 0xFF, 0xFF, 0xFF, 0xFF])
        result = decode("CT", data)

        assert result[0] == [[10, 20], [12, 30]]
        assert result[1] == [[14, 0], [18, 50]]

    def test_decode_too_short_raises(self) -> None:
        """CT requires 8 bytes.

        Technique: Boundary Value Analysis.
        """
        with pytest.raises(CodecError, match="8 bytes"):
            decode("CT", b"\x30\x30\x30")

    def test_encode_simple_schedule(self) -> None:
        """Technique: Round-trip Testing."""
        schedule = [
            [[6, 0], [22, 0]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]
        encoded = encode("CT", schedule)
        assert encoded == bytes([0x30, 0xB0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])

    def test_roundtrip(self) -> None:
        """Encode then decode preserves schedule.

        Technique: Round-trip Testing.
        """
        schedule = [
            [[10, 20], [12, 30]],
            [[14, 0], [18, 50]],
            [[None, None], [None, None]],
            [[None, None], [None, None]],
        ]
        encoded = encode("CT", schedule)
        decoded = decode("CT", encoded)
        assert decoded == schedule


# ---------------------------------------------------------------------------
# TI — SystemTime (BCD datetime)
# ---------------------------------------------------------------------------


class TestTI:
    """TI: BCD-packed system time → datetime."""

    def test_decode_known_datetime(self) -> None:
        """2026-02-28 14:30:00.

        Byte layout: year_hi, year_lo, month, day, weekday,
                     hour, minute, second

        Technique: Specification-based.
        """
        data = bytes([0x20, 0x26, 0x02, 0x28, 0x06, 0x14, 0x30, 0x00])
        result = decode("TI", data)
        assert result == datetime(2026, 2, 28, 14, 30, 0)

    def test_decode_midnight(self) -> None:
        """Midnight: 2025-01-01 00:00:00.

        Technique: Boundary Value Analysis — midnight.
        """
        data = bytes([0x20, 0x25, 0x01, 0x01, 0x03, 0x00, 0x00, 0x00])
        assert decode("TI", data) == datetime(2025, 1, 1, 0, 0, 0)

    def test_decode_too_short_raises(self) -> None:
        """TI requires 8 bytes.

        Technique: Boundary Value Analysis.
        """
        with pytest.raises(CodecError, match="8 bytes"):
            decode("TI", b"\x20\x26\x02")

    def test_encode_not_supported(self) -> None:
        """TI encoding not implemented (legacy never wrote it).

        Technique: Error Guessing.
        """
        with pytest.raises(CodecError, match="not supported"):
            encode("TI", datetime(2026, 1, 1))


# ---------------------------------------------------------------------------
# Public API: unknown type codes
# ---------------------------------------------------------------------------


class TestUnknownTypeCode:
    """Unknown or excluded type codes raise CodecError."""

    def test_decode_unknown_raises(self) -> None:
        """Technique: Error Guessing — typo or excluded type."""
        with pytest.raises(CodecError, match="Unknown type code"):
            decode("BOGUS", b"\x00")

    def test_encode_unknown_raises(self) -> None:
        """Technique: Error Guessing."""
        with pytest.raises(CodecError, match="Unknown type code"):
            encode("BOGUS", 0)

    @pytest.mark.parametrize("excluded", ["IS100", "IU2", "IU10", "OO", "DT", "F_E"])
    def test_excluded_legacy_types_raise(self, excluded: str) -> None:
        """Types not used by Vitodens 200-W are explicitly excluded.

        Technique: Specification-based — scope per revised plan.
        """
        with pytest.raises(CodecError, match="Unknown type code"):
            decode(excluded, b"\x00")


# ---------------------------------------------------------------------------
# BCD datetime error wrapping
# ---------------------------------------------------------------------------


class TestBCDDatetimeErrors:
    """Invalid BCD bytes must raise CodecError, not raw ValueError.

    The public decode() contract says only CodecError escapes.
    Internal ValueError/OverflowError from BCD parsing or datetime
    construction must be wrapped.

    Technique: Contract correctness — exception wrapping.
    """

    def _make_es_data_raw(self, error_code: int, timestamp_bytes: bytes) -> bytes:
        """Build ES data with a custom timestamp (may be invalid BCD)."""
        return bytes([error_code]) + timestamp_bytes

    def test_non_bcd_nibble_raises_codec_error(self) -> None:
        """BCD byte 0x2A has non-decimal nibble → CodecError.

        int("2A") raises ValueError; this must become CodecError.

        Technique: Error Guessing — corrupted BCD data from hardware.
        """
        # 0x2A in the month position will produce int("2A") → ValueError
        bad_timestamp = bytes([0x20, 0x26, 0x2A, 0x28, 0x06, 0x14, 0x30, 0x00])
        data = self._make_es_data_raw(0x00, bad_timestamp)
        with pytest.raises(CodecError, match="Invalid BCD datetime"):
            decode("ES", data, language="en")

    def test_invalid_date_raises_codec_error(self) -> None:
        """BCD month 0x13 (13) is valid BCD but invalid date → CodecError.

        datetime(2026, 13, 1) raises ValueError; must become CodecError.

        Technique: Error Guessing — out-of-range BCD date field.
        """
        bad_timestamp = bytes([0x20, 0x26, 0x13, 0x01, 0x01, 0x00, 0x00, 0x00])
        data = self._make_es_data_raw(0x00, bad_timestamp)
        with pytest.raises(CodecError, match="Invalid BCD datetime"):
            decode("ES", data, language="en")

    def test_ti_invalid_bcd_raises_codec_error(self) -> None:
        """TI type also wraps BCD errors as CodecError.

        Technique: Equivalence Partitioning — same BCD path via TI.
        """
        bad_data = bytes([0x20, 0x26, 0x2F, 0x28, 0x06, 0x14, 0x30, 0x00])
        with pytest.raises(CodecError, match="Invalid BCD datetime"):
            decode("TI", bad_data)


# ---------------------------------------------------------------------------
# Encode error messages show labels not codes
# ---------------------------------------------------------------------------


class TestEncodeErrorMessages:
    """Verify that codec error messages show valid label strings,
    not internal integer byte codes.

    Technique: Specification-based — error message usability.
    """

    def test_ba_error_shows_labels_not_codes(self) -> None:
        """BA encode error lists valid labels like 'off', 'reduced', etc.

        Technique: Error Guessing — user sees helpful error on typo.
        """
        with pytest.raises(CodecError, match="off") as exc_info:
            encode("BA", "bogus_label", language="en")
        msg = str(exc_info.value)
        # Should contain label strings, not integer codes
        assert "off" in msg
        assert "reduced" in msg
        # Should NOT contain raw integer codes
        assert "[0," not in msg

    def test_usv_error_shows_labels_not_codes(self) -> None:
        """USV encode error lists valid labels like 'heating', 'middle', etc.

        Technique: Error Guessing — user sees helpful error on typo.
        """
        with pytest.raises(CodecError, match="heating") as exc_info:
            encode("USV", "bogus_label", language="en")
        msg = str(exc_info.value)
        assert "heating" in msg
        assert "middle" in msg
        assert "[0," not in msg
