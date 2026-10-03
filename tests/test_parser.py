"""Sociable unit tests for the Roland Super-MRC binary parser.

Tests observable decoding behavior, timing accuracy, gate times,
and domain exception handling.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from roland_super_mrc.exceptions import CorruptHeaderError
from roland_super_mrc.parser import decode_tempo_track, parse_sng_bytes, parse_sng_file
from tests.conftest import create_minimal_sng_binary


def test_parse_valid_sng_file(sample_sng_path: Path) -> None:
    """Verify parsing a valid SNG file returns complete SuperMrcSong."""
    song = parse_sng_file(sample_sng_path)

    assert song.title == "AUTUMN GROOVE"
    assert song.initial_tempo_bpm == 124
    assert song.time_signature == (4, 4)
    assert song.ppqn == 96
    assert len(song.performance_tracks) == 1
    assert song.performance_tracks[0].track_number == 1

    # Check Note-On and scheduled Note-Off events
    events = song.performance_tracks[0].events
    note_ons = [e for e in events if e.status == 0x90]
    note_offs = [e for e in events if e.status == 0x80]

    assert len(note_ons) == 2
    assert len(note_offs) == 2

    # First note: C4 (60), tick 0, gate 96 -> Note-Off at tick 96
    assert note_ons[0].tick == 0
    assert note_ons[0].data1 == 60
    assert note_ons[0].data2 == 100
    assert note_offs[0].tick == 96
    assert note_offs[0].data1 == 60

    # Second note: E4 (64), delta 96 (tick 96), gate 48 -> Note-Off at tick 144
    assert note_ons[1].tick == 96
    assert note_ons[1].data1 == 64
    assert note_offs[1].tick == 96 + 48


def test_parse_header_too_small_raises_corrupt_header_error() -> None:
    """Verify that buffers smaller than 0x200 raise CorruptHeaderError."""
    short_data = b"ROLAND MC-50 SHORT"
    with pytest.raises(CorruptHeaderError, match="File too small for Roland Super-MRC header"):
        parse_sng_bytes(short_data)


def test_parse_nonexistent_file_raises_file_not_found(tmp_path: Path) -> None:
    """Verify clean FileNotFoundError when given missing file path."""
    missing = tmp_path / "DOES_NOT_EXIST.SNG"
    with pytest.raises(FileNotFoundError):
        parse_sng_file(missing)


def test_fe_skip_timing_opcode_advances_ticks() -> None:
    """Verify that 0xFE skip opcode correctly advances the tick accumulator by count * 256."""
    # Build raw track with FE opcode: FE 00 02 00 00 00 (skips 2 * 256 = 512 ticks)
    # Then Note-On at delta 10
    trk_events = bytearray()
    trk_events.extend(bytes([0xFE, 0, 2, 0, 0, 0]))  # +512 ticks
    trk_events.extend(bytes([0x90, 10, 60, 100, 48, 0]))  # +10 ticks -> tick 522
    trk_events.append(0xFF)

    # Wrap in minimal SNG
    sng_data = bytearray(create_minimal_sng_binary())
    trk1_offset = sng_data[0x40] | (sng_data[0x41] << 8) | (sng_data[0x42] << 16)
    sng_data[trk1_offset : trk1_offset + len(trk_events)] = trk_events
    # Update length
    sng_data[0x43] = len(trk_events) & 0xFF
    sng_data[0x44] = (len(trk_events) >> 8) & 0xFF

    song = parse_sng_bytes(bytes(sng_data))
    note_ons = [e for e in song.performance_tracks[0].events if e.status == 0x90]

    assert len(note_ons) == 1
    assert note_ons[0].tick == 522


def test_tempo_track_fixed_point_ratio() -> None:
    """Verify conductor track correctly decodes 0xF9 fixed-point 8.8 tempo ratio."""
    # 0xF9 event: st=0xF9, delta=96, w1=384 (1.5x of 120 = 180 BPM), pad=0, 0
    # w1 = 384 = 0x0180 (lo=0x80, hi=0x01)
    tempo_stream = bytearray()
    tempo_stream.extend(bytes([0xF9, 96, 0x80, 0x01, 0, 0]))
    tempo_stream.append(0xFF)

    events = decode_tempo_track(
        bytes(tempo_stream), slot3_ptr=0, slot3_len=len(tempo_stream), initial_bpm=120
    )

    assert len(events) == 1
    assert events[0].tick == 96
    assert events[0].bpm == 180.0
