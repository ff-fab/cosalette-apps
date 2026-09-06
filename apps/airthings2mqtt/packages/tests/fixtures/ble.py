"""Captured raw BLE frames from real Airthings devices, for decode tests.

The Wave 2 sample is an early-adopter field capture (ff-fab, 2026-09-05):
20 bytes read from the "Current Sensor Values" characteristic
``b42e4dcc-ade7-11e4-89d3-123b93f75cba`` of an Airthings Wave2 (2nd-gen,
model 2950). Decoded values were cross-checked against a co-located 1st-gen
Wave and the official Airthings app at the same time. See
``docs/planning/wave2-protocol-support.md``.
"""

from __future__ import annotations

# Raw read #1 from the capture: humidity 33.5 %RH, radon 24h 134, radon
# long-term 106, temperature 33.31 °C. The unit sat in a warm server closet.
WAVE2_SAMPLE_2950 = bytes.fromhex("0143010086006a00030dffffffffffff0000ffff")

# Raw read #2, 8 minutes later: byte 2 (a status/ambient-light byte the parser
# ignores) toggled 0x01 -> 0x00; every measured quantity held constant.
WAVE2_SAMPLE_2950_STATUS_BYTE_CLEARED = bytes.fromhex(
    "0143000086006a00030dffffffffffff0000ffff"
)

WAVE2_SAMPLE_2950_DECODED = {
    "temperature": 33.31,
    "humidity": 33.5,
    "radon_24h_avg": 134,
    "radon_long_term_avg": 106,
}
