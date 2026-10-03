"""Binary parser for Roland Super-MRC (.SNG) song files."""

from __future__ import annotations

from pathlib import Path

from roland_super_mrc.exceptions import CorruptHeaderError
from roland_super_mrc.models import (
    PerformanceTrack,
    SuperMrcSong,
    TempoEvent,
    TimedMidiEvent,
)
from roland_super_mrc.rhythm import (
    DEFAULT_VELOCITY_TABLE,
    PPQN,
    decode_rhythm_stream,
    parse_drum_palette,
)

MIN_HEADER_SIZE = 0x200


def read_24bit_le(data: bytes, offset: int) -> int:
    """Read a 3-byte little-endian unsigned integer."""
    if offset + 3 > len(data):
        return 0
    return data[offset] | (data[offset + 1] << 8) | (data[offset + 2] << 16)


def _decode_note_on_off(
    cur_tick: int,
    channel: int,
    chunk: bytes,
) -> tuple[TimedMidiEvent, TimedMidiEvent]:
    """Emit deterministic Note-On and Note-Off events from a 6-byte note record."""
    note = chunk[2]
    vel = chunk[3]
    gate = chunk[4] | (chunk[5] << 8)

    note_on = TimedMidiEvent(
        tick=cur_tick,
        status=0x90,
        channel=channel,
        data1=note,
        data2=vel,
        gate_ticks=gate,
    )
    note_off = TimedMidiEvent(
        tick=cur_tick + gate,
        status=0x80,
        channel=channel,
        data1=note,
        data2=64,
    )
    return note_on, note_off


def _decode_single_record(
    chunk: bytes,
    cur_tick: int,
) -> tuple[list[TimedMidiEvent], int]:
    """Decode a single 6-byte record into TimedMidiEvents and tick advancement."""
    st = chunk[0]
    status_type = st & 0xF0
    ch = st & 0x0F
    delta = chunk[1]
    effective_tick = cur_tick + delta

    if st == 0xFE:
        count = chunk[2]
        return [], delta + (count * 256)

    if status_type == 0x90:
        on_ev, off_ev = _decode_note_on_off(effective_tick, ch, chunk)
        return [on_ev, off_ev], delta

    if status_type == 0xC0:
        prog = chunk[2]
        ev = TimedMidiEvent(tick=effective_tick, status=0xC0, channel=ch, data1=prog, data2=0)
        return [ev], delta

    if status_type in (0xB0, 0xE0, 0xA0, 0xD0):
        ev = TimedMidiEvent(
            tick=effective_tick, status=status_type, channel=ch, data1=chunk[2], data2=chunk[3]
        )
        return [ev], delta

    return [], delta


def decode_performance_stream(
    data: bytes,
    start_offset: int,
    end_offset: int,
    track_num: int,
) -> list[TimedMidiEvent]:
    """Decode a single 6-byte event record stream for Tracks 1 to 8."""
    if start_offset >= len(data) or end_offset > len(data) or start_offset >= end_offset:
        return []

    events: list[TimedMidiEvent] = []
    cursor = start_offset
    cur_tick = 0

    while cursor + 5 < end_offset:
        if data[cursor] == 0xFF:  # End of track marker
            break

        chunk = data[cursor : cursor + 6]
        cursor += 6

        new_events, advance = _decode_single_record(chunk, cur_tick)
        cur_tick += advance
        events.extend(new_events)

    return events


def decode_tempo_track(
    data: bytes,
    slot3_ptr: int,
    slot3_len: int = 0,
    initial_bpm: int = 120,
) -> list[TempoEvent]:
    """Decode conductor / tempo track stored at 0x0030 using fixed-point 8.8 tempo ratio."""
    if slot3_ptr < 0 or slot3_ptr >= len(data):
        return []

    end_ptr = min(len(data), slot3_ptr + slot3_len) if slot3_len > 0 else len(data)
    tempo_changes: list[TempoEvent] = []
    cur = slot3_ptr
    cur_tick = 0

    while cur + 5 < end_ptr:
        cmd = data[cur]
        if cmd == 0xFF:
            break
        delta = data[cur + 1]
        cur_tick += delta

        if cmd == 0xFE:
            count = data[cur + 2]
            cur_tick += count * 256
        elif cmd == 0xF9:
            # Bytes 2-3 are fixed-point 8.8 tempo ratio (256 = 1.0x initial tempo)
            w1 = data[cur + 2] | (data[cur + 3] << 8)
            if w1 > 0:
                bpm = max(20.0, min(350.0, round(initial_bpm * (w1 / 256.0))))
                tempo_changes.append(TempoEvent(tick=cur_tick, bpm=float(bpm)))

        cur += 6

    return tempo_changes


def _extract_song_title(data: bytes, fallback_title: str | None) -> str:
    """Extract space-trimmed Latin-1 song title from header offset 0x0000."""
    raw_title = data[0:16].decode("latin1", errors="replace").strip()
    return raw_title or fallback_title or "Untitled"


def _extract_song_end(data: bytes) -> int:
    """Extract 24-bit song end boundary pointer from offset 0x0010."""
    song_end = read_24bit_le(data, 0x0010)
    if song_end == 0 or song_end > len(data):
        return len(data)
    return song_end


def _extract_initial_bpm(data: bytes) -> int:
    """Extract initial tempo in BPM from offset 0x00F1."""
    return data[0x00F1] if data[0x00F1] > 0 else 120


def _extract_time_signature(data: bytes) -> tuple[int, int]:
    """Detect beats per measure from first pattern descriptor or default to 4/4."""
    default_beats = 4
    if len(data) > 0x02A5:
        b = data[0x02A0 + 5]
        if b in (2, 3, 4, 5, 6, 7, 8, 12):
            default_beats = b
    return (default_beats, 4)


def _extract_velocity_table(data: bytes) -> tuple[int, ...]:
    """Extract custom 8-level velocity scale or return default curve."""
    custom_vel = list(data[0x0120:0x0128])
    return tuple(custom_vel) if any(custom_vel) else DEFAULT_VELOCITY_TABLE


def _parse_all_performance_tracks(data: bytes, song_end: int) -> list[PerformanceTrack]:
    """Parse performance track descriptors at offsets 0x0040 to 0x00B0."""
    perf_tracks: list[PerformanceTrack] = []
    for trk_idx in range(8):
        slot_off = 0x0040 + (trk_idx * 16)
        start_ptr = read_24bit_le(data, slot_off)
        trk_len = read_24bit_le(data, slot_off + 3)

        if trk_len > 0 and 0 < start_ptr < song_end:
            next_ptr = min(song_end, start_ptr + trk_len)
            events = decode_performance_stream(data, start_ptr, next_ptr, trk_idx + 1)
            if events:
                perf_tracks.append(
                    PerformanceTrack(
                        track_number=trk_idx + 1,
                        name=f"Track {trk_idx + 1}",
                        events=tuple(events),
                    )
                )
    return perf_tracks


def _calculate_pattern_table_limit(
    data: bytes,
    slot12_ptr: int,
    slot2_ptr: int,
    slot3_ptr: int,
) -> int:
    """Find the earliest stream pointer after 0x02A0 to avoid reading track notes as patterns."""
    candidates: list[int] = []
    for trk_idx in range(8):
        slot_off = 0x0040 + (trk_idx * 16)
        start_ptr = read_24bit_le(data, slot_off)
        trk_len = read_24bit_le(data, slot_off + 3)
        if trk_len > 0 and start_ptr > 0x02A0:
            candidates.append(start_ptr)

    for ptr in (slot2_ptr, slot3_ptr, slot12_ptr):
        if ptr > 0x02A0:
            candidates.append(ptr)

    return min(candidates) if candidates else len(data)


def parse_sng_bytes(data: bytes, fallback_title: str | None = None) -> SuperMrcSong:
    """Parse raw Super-MRC binary bytes into a SuperMrcSong model."""
    if len(data) < MIN_HEADER_SIZE:
        raise CorruptHeaderError(
            f"File too small for Roland Super-MRC header: {len(data)} bytes (minimum {MIN_HEADER_SIZE})."
        )

    title = _extract_song_title(data, fallback_title)
    song_end = _extract_song_end(data)
    initial_bpm = _extract_initial_bpm(data)
    time_signature = _extract_time_signature(data)
    vel_table = _extract_velocity_table(data)
    palette = parse_drum_palette(data)

    perf_tracks = _parse_all_performance_tracks(data, song_end)

    slot12_ptr = read_24bit_le(data, 0x00C0)
    slot2_ptr = read_24bit_le(data, 0x0020)
    slot3_ptr = read_24bit_le(data, 0x0030)
    slot3_len = read_24bit_le(data, 0x0033)

    pat_limit = _calculate_pattern_table_limit(data, slot12_ptr, slot2_ptr, slot3_ptr)
    rhythm_events, measure_count = decode_rhythm_stream(
        data, slot12_ptr, slot2_ptr, palette, vel_table, pattern_table_limit=pat_limit
    )

    tempo_changes = (
        decode_tempo_track(data, slot3_ptr, slot3_len=slot3_len, initial_bpm=initial_bpm)
        if 0 < slot3_ptr < len(data)
        else []
    )

    return SuperMrcSong(
        title=title,
        initial_tempo_bpm=initial_bpm,
        time_signature=time_signature,
        ppqn=PPQN,
        performance_tracks=tuple(perf_tracks),
        rhythm_events=tuple(rhythm_events),
        tempo_changes=tuple(tempo_changes),
        measure_count=measure_count,
    )


def parse_sng_file(path: Path) -> SuperMrcSong:
    """Read and parse a Roland Super-MRC file from disk."""
    if not path.is_file():
        raise FileNotFoundError(f"Super-MRC file not found: {path}")

    data = path.read_bytes()
    fallback_title = path.stem
    return parse_sng_bytes(data, fallback_title=fallback_title)
