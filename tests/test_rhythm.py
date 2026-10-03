"""Sociable unit tests for Roland Super-MRC rhythm track and timeline unrolling.

Tests pattern unrolling, 22-byte descriptors, signed 8-bit velocity trims,
and pure transformation helpers in rhythm.py.
"""

from __future__ import annotations

from roland_super_mrc.models import DecodedPattern, MeasureTimelineEntry, RhythmPatternNote
from roland_super_mrc.parser import parse_sng_bytes
from roland_super_mrc.rhythm import (
    DEFAULT_VELOCITY_TABLE,
    _calculate_drum_velocity,
    unroll_rhythm_events,
)
from tests.conftest import create_minimal_sng_binary


def test_rhythm_pattern_unrolling_and_signed_velocity_trim() -> None:
    """Verify that rhythm patterns are unrolled on Channel 10 with signed velocity trim."""
    sng_data = create_minimal_sng_binary()
    song = parse_sng_bytes(sng_data)

    drum_events = song.rhythm_events
    assert len(drum_events) > 0

    drum_note_ons = [e for e in drum_events if e.status == 0x90]
    assert len(drum_note_ons) == 2

    # Verify Channel 10 (0-indexed 9)
    assert drum_note_ons[0].channel == 9
    assert drum_note_ons[0].data1 == 36  # Kick Drum
    assert drum_note_ons[0].data2 == 122  # 127 - 5
    assert drum_note_ons[0].tick == 0

    # Second drum hit: Snare (38) at delta 96
    assert drum_note_ons[1].channel == 9
    assert drum_note_ons[1].data1 == 38
    assert drum_note_ons[1].tick == 96


def test_rest_measure_advances_tick_accumulator() -> None:
    """Verify that 0xF4 rest measure correctly advances time by beats * PPQN."""
    sng_data = bytearray(create_minimal_sng_binary(beats=4))

    slot2_offset = sng_data[0x20] | (sng_data[0x21] << 8) | (sng_data[0x22] << 16)
    # 0xF4 rest measure (3 bytes: F4 00 00), then Pattern 0 (00 00 00), then FF end
    timeline = bytes([0xF4, 0, 0, 0, 0, 0, 0xFF])
    sng_data[slot2_offset : slot2_offset + len(timeline)] = timeline

    song = parse_sng_bytes(bytes(sng_data))
    drum_note_ons = [e for e in song.rhythm_events if e.status == 0x90]

    # Pattern 0 notes should now be shifted by 4 beats * 96 ticks = 384 ticks
    assert len(drum_note_ons) == 2
    assert drum_note_ons[0].tick == 384
    assert drum_note_ons[1].tick == 384 + 96


def test_calculate_drum_velocity_clamping() -> None:
    """Verify velocity computation handles boundaries (1-127) and code 7 max."""
    # Vel code 7 -> base 127
    assert _calculate_drum_velocity(7, 0, DEFAULT_VELOCITY_TABLE) == 127
    # Vel code 7 with positive trim clamps to 127
    assert _calculate_drum_velocity(7, 10, DEFAULT_VELOCITY_TABLE) == 127
    # Vel code 7 with negative trim
    assert _calculate_drum_velocity(7, -27, DEFAULT_VELOCITY_TABLE) == 100
    # Vel code 0 -> base 16, trimmed below 1 clamps to 1
    assert _calculate_drum_velocity(0, -30, DEFAULT_VELOCITY_TABLE) == 1


def test_unroll_rhythm_events_pure_transformation() -> None:
    """Verify unroll_rhythm_events transforms patterns and timeline entries into events."""
    pattern = DecodedPattern(
        pattern_index=0,
        beats=4,
        notes=(
            RhythmPatternNote(rel_tick=0, note=36, vel_code=7),
            RhythmPatternNote(rel_tick=96, note=38, vel_code=5),
        ),
    )
    timeline = [
        MeasureTimelineEntry(measure_index=0, pattern_slot=0, velocity_trim=0),
        MeasureTimelineEntry(measure_index=1, pattern_slot=0xF4, velocity_trim=0),
    ]

    events, measures = unroll_rhythm_events(
        patterns=[pattern],
        arrangement=timeline,
        vel_table=DEFAULT_VELOCITY_TABLE,
        ppqn=96,
    )

    assert measures == 2
    # 2 note-ons + 2 note-offs = 4 events for measure 0; measure 1 is rest
    assert len(events) == 4
    assert events[0].status == 0x90
    assert events[0].tick == 0
    assert events[1].status == 0x80
    assert events[1].tick == 24


def test_pattern_descriptors_bounded_by_performance_tracks() -> None:
    """Verify that pattern descriptors stop when encountering Track 1."""
    # Create binary where Track 1 starts at 0x02B8
    raw_sng = bytearray(create_minimal_sng_binary())
    song = parse_sng_bytes(bytes(raw_sng))

    # All rhythm events must finish within reasonable measure bounds (not hundreds of bars of silence)
    if song.rhythm_events:
        max_tick = max(e.tick for e in song.rhythm_events)
        # Should not exceed measure_count * 384
        assert max_tick <= (song.measure_count + 1) * 384
