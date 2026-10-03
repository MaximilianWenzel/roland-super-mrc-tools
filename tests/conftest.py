"""Pytest fixtures and synthetic Super-MRC binary builders."""

from __future__ import annotations

from pathlib import Path

import pytest


def create_minimal_sng_binary(
    title: str = "TEST SONG",
    bpm: int = 120,
    beats: int = 4,
    notes: list[tuple[int, int, int, int]] | None = None,
) -> bytes:
    """Construct an authentic, bit-compliant Roland Super-MRC binary chunk.

    notes: list of (delta, note, velocity, gate_ticks)
    """
    if notes is None:
        notes = [(0, 60, 100, 96), (96, 64, 90, 48)]

    # Build Performance Track 1 Event Stream (6-byte tuples)
    trk1_stream = bytearray()
    for delta, note, vel, gate in notes:
        gate_lo = gate & 0xFF
        gate_hi = (gate >> 8) & 0xFF
        trk1_stream.extend(bytes([0x90, delta, note, vel, gate_lo, gate_hi]))
    trk1_stream.append(0xFF)  # End of track

    # Build Rhythm Note Stream and Patterns
    slot12_stream = bytearray()
    # Pattern 0 note stream: 3-byte tuples [b0, b1, b2]
    # Drum note Kick (36) at delta 0, vel_code 7
    slot12_stream.extend(bytes([36, 0, 7]))
    # Snare (38) at delta 96, vel_code 5
    slot12_stream.extend(bytes([38, 96, 5]))
    slot12_stream.append(0xFF)  # End of pattern

    # Build Measure Timeline (Slot 2 at 0x0020)
    # Measure 0: 3-byte record [pattern_slot=0, reserved=0, velocity_trim=-5 (signed 0xFB)]
    timeline_stream = bytearray(bytes([0, 0, 0xFB]))
    timeline_stream.append(0xFF)  # End of timeline

    # Calculate Offsets
    header_len = 0x300
    slot2_offset = header_len
    slot12_offset = slot2_offset + len(timeline_stream)
    trk1_offset = slot12_offset + len(slot12_stream)
    total_len = trk1_offset + len(trk1_stream)

    buf = bytearray(total_len)

    # Header: Song Title at 0x0000 (16 bytes)
    title_bytes = title.encode("latin1")[:16].ljust(16, b" ")
    buf[0:16] = title_bytes

    # Song End Pointer at 0x0010 (3 bytes LE)
    buf[0x10] = total_len & 0xFF
    buf[0x11] = (total_len >> 8) & 0xFF
    buf[0x12] = (total_len >> 16) & 0xFF

    # Slot 2 Timeline Pointer at 0x0020
    buf[0x20] = slot2_offset & 0xFF
    buf[0x21] = (slot2_offset >> 8) & 0xFF
    buf[0x22] = (slot2_offset >> 16) & 0xFF

    # Track 1 Descriptor at 0x0040 (offset 3 bytes, length 3 bytes)
    buf[0x40] = trk1_offset & 0xFF
    buf[0x41] = (trk1_offset >> 8) & 0xFF
    buf[0x42] = (trk1_offset >> 16) & 0xFF
    trk1_len = len(trk1_stream)
    buf[0x43] = trk1_len & 0xFF
    buf[0x44] = (trk1_len >> 8) & 0xFF
    buf[0x45] = (trk1_len >> 16) & 0xFF

    # Slot 12 Rhythm Notes Pointer at 0x00C0
    buf[0xC0] = slot12_offset & 0xFF
    buf[0xC1] = (slot12_offset >> 8) & 0xFF
    buf[0xC2] = (slot12_offset >> 16) & 0xFF

    # Initial Tempo BPM at 0x00F1
    buf[0xF1] = bpm & 0xFF

    # Pattern Descriptor 0 at 0x02A0 (22 bytes)
    # byte 0: pattern index (0)
    buf[0x02A0] = 0
    # bytes 1-2: relative offset in slot 12 (0)
    buf[0x02A1] = 0
    buf[0x02A2] = 0
    # byte 5: beats per measure
    buf[0x02A5] = beats

    # Copy streams into buffer
    buf[slot2_offset : slot2_offset + len(timeline_stream)] = timeline_stream
    buf[slot12_offset : slot12_offset + len(slot12_stream)] = slot12_stream
    buf[trk1_offset : trk1_offset + len(trk1_stream)] = trk1_stream

    return bytes(buf)


@pytest.fixture
def sample_sng_path(tmp_path: Path) -> Path:
    """Fixture providing a minimal, valid .SNG file path on disk."""
    sng_bytes = create_minimal_sng_binary(title="AUTUMN GROOVE", bpm=124, beats=4)
    file_path = tmp_path / "AUTUMN.SNG"
    file_path.write_bytes(sng_bytes)
    return file_path
