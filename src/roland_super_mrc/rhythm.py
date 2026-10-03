"""Rhythm pattern unpacker and timeline unroller for Roland Super-MRC."""

from __future__ import annotations

from typing import Sequence

from roland_super_mrc.models import (
    DecodedPattern,
    MeasureTimelineEntry,
    RhythmPatternNote,
    TimedMidiEvent,
)

PPQN = 96
DRUM_GATE_TICKS = 24  # Standard drum duration (16th note)
DEFAULT_VELOCITY_TABLE: tuple[int, ...] = (16, 32, 48, 64, 80, 96, 112, 127)


def parse_drum_palette(data: bytes) -> dict[int, int]:
    """Extract drum instrument mapping from header offset 0x0130.

    128 2-byte tuples: [0x09, midi_note].
    """
    palette: dict[int, int] = {}
    for i in range(128):
        off = 0x0130 + (i * 2)
        if off + 1 < len(data) and data[off] == 0x09:
            note_val = data[off + 1]
            if note_val == 3:
                note_val = 36  # Standard GM Bass Drum 1 (Kick)
            elif note_val == 118:
                note_val = 41  # Low Floor Tom
            palette[i] = note_val
        else:
            palette[i] = i
    return palette


def _decompress_pattern_notes(
    data: bytes,
    note_stream_offset: int,
    drum_palette: dict[int, int],
) -> tuple[RhythmPatternNote, ...]:
    """Extract 3-byte drum note tuples [rel_tick, note, vel_code] from a pattern stream."""
    notes: list[RhythmPatternNote] = []
    c = note_stream_offset
    rel_tick = 0

    while c + 2 < len(data):
        b0 = data[c]
        b1 = data[c + 1]
        b2 = data[c + 2]
        c += 3

        if b0 == 0xFF:
            break
        if b0 == 0xFE:
            rel_tick += b1 + (b2 << 8)
            continue

        rel_tick += b1
        sound_idx = b0 & 0x7F
        note = drum_palette.get(sound_idx, sound_idx)
        notes.append(RhythmPatternNote(rel_tick=rel_tick, note=note, vel_code=b2))

    return tuple(notes)


def parse_pattern_descriptors(
    data: bytes,
    slot12_ptr: int,
    drum_palette: dict[int, int],
    pattern_table_limit: int | None = None,
) -> list[DecodedPattern]:
    """Parse 22-byte pattern descriptor table at offset 0x02A0."""
    patterns: list[DecodedPattern] = []
    cur_pat_hdr = 0x02A0
    upper_limit = (
        slot12_ptr if pattern_table_limit is None else min(slot12_ptr, pattern_table_limit)
    )

    while cur_pat_hdr + 22 <= upper_limit:
        chunk = data[cur_pat_hdr : cur_pat_hdr + 22]
        p_num = chunk[0]
        p_off = chunk[1] | (chunk[2] << 8)
        beats = chunk[5] if chunk[5] > 0 else 4

        notes = _decompress_pattern_notes(data, slot12_ptr + p_off, drum_palette)
        patterns.append(
            DecodedPattern(
                pattern_index=p_num,
                beats=beats,
                notes=notes,
            )
        )
        cur_pat_hdr += 22

    return patterns


def _decode_timeline_entry(data: bytes, offset: int, measure_idx: int) -> MeasureTimelineEntry:
    """Decode a single 3-byte measure timeline record [pattern_slot, reserved, velocity_trim]."""
    p_num = data[offset]
    trim_byte = data[offset + 2]
    # trim_byte at offset + 2 is a signed 8-bit velocity trim (-128 .. +127)
    vel_trim = trim_byte if trim_byte < 128 else (trim_byte - 256)
    return MeasureTimelineEntry(
        measure_index=measure_idx,
        pattern_slot=p_num,
        velocity_trim=vel_trim,
    )


def parse_measure_timeline(data: bytes, slot2_ptr: int) -> list[MeasureTimelineEntry]:
    """Parse measure arrangement records stored at Slot 2 pointer (0x0020)."""
    arrangement: list[MeasureTimelineEntry] = []
    cur_arr = slot2_ptr
    m_idx = 0

    while cur_arr + 2 < len(data):
        if data[cur_arr] == 0xFF:
            break
        entry = _decode_timeline_entry(data, cur_arr, m_idx)
        arrangement.append(entry)
        cur_arr += 3
        m_idx += 1

    return arrangement


def _calculate_drum_velocity(vel_code: int, trim: int, vel_table: Sequence[int]) -> int:
    """Compute bounded MIDI velocity (1-127) from velocity code and measure trim."""
    if vel_code == 7 or vel_code >= len(vel_table):
        base_v = 127
    else:
        base_v = vel_table[vel_code]
    return max(1, min(127, base_v + trim))


def _unroll_pattern_notes(
    entry: MeasureTimelineEntry,
    pat: DecodedPattern,
    cur_tick: int,
    vel_table: Sequence[int],
) -> list[TimedMidiEvent]:
    """Emit Note-On and Note-Off events on MIDI Channel 10 for a single measure."""
    events: list[TimedMidiEvent] = []

    for item in pat.notes:
        final_vel = _calculate_drum_velocity(item.vel_code, entry.velocity_trim, vel_table)
        t_on = cur_tick + item.rel_tick
        t_off = t_on + DRUM_GATE_TICKS

        # MIDI Channel 10 is 0-indexed as 9
        events.append(
            TimedMidiEvent(
                tick=t_on,
                status=0x90,
                channel=9,
                data1=item.note,
                data2=final_vel,
                gate_ticks=DRUM_GATE_TICKS,
            )
        )
        events.append(
            TimedMidiEvent(
                tick=t_off,
                status=0x80,
                channel=9,
                data1=item.note,
                data2=64,
            )
        )

    return events


def unroll_rhythm_events(
    patterns: Sequence[DecodedPattern],
    arrangement: Sequence[MeasureTimelineEntry],
    vel_table: Sequence[int],
    ppqn: int = PPQN,
) -> tuple[list[TimedMidiEvent], int]:
    """Unroll measure timeline and pattern notes into an absolute Channel 10 event stream."""
    drum_events: list[TimedMidiEvent] = []
    cur_tick = 0
    default_beats = patterns[0].beats if patterns else 4

    for entry in arrangement:
        if entry.pattern_slot == 0xF4:
            # Rest measure (silence)
            cur_tick += default_beats * ppqn
            continue

        if entry.pattern_slot < len(patterns):
            pat = patterns[entry.pattern_slot]
            measure_len = pat.beats * ppqn
            drum_events.extend(_unroll_pattern_notes(entry, pat, cur_tick, vel_table))
            cur_tick += measure_len
        else:
            cur_tick += default_beats * ppqn

    return drum_events, len(arrangement)


def decode_rhythm_stream(
    data: bytes,
    slot12_ptr: int,
    slot2_ptr: int,
    drum_palette: dict[int, int],
    vel_table: Sequence[int],
    pattern_table_limit: int | None = None,
) -> tuple[list[TimedMidiEvent], int]:
    """Decode rhythm pattern definitions and unroll the timeline onto Channel 10."""
    if slot12_ptr == 0 or slot12_ptr >= len(data) or slot2_ptr == 0 or slot2_ptr >= len(data):
        return [], 0

    patterns = parse_pattern_descriptors(
        data, slot12_ptr, drum_palette, pattern_table_limit=pattern_table_limit
    )
    if not patterns:
        return [], 0

    arrangement = parse_measure_timeline(data, slot2_ptr)
    return unroll_rhythm_events(patterns, arrangement, vel_table)
