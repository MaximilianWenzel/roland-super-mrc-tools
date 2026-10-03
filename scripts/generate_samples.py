"""Generate authentic, jazzy sample Roland Super-MRC files for examples/."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from roland_super_mrc.parser import parse_sng_file

PPQN = 96
BAR = 384


def _encode_performance_stream(
    events: Sequence[tuple[int, int, int, int]],
    channel: int,
    program: int | None = None,
) -> bytes:
    """Encode timed note events (tick, note, velocity, gate) into a 6-byte Super-MRC stream."""
    stream = bytearray()
    if program is not None:
        stream.extend(bytes([0xC0 | (channel & 0x0F), 0, program, 0, 0, 0]))

    last_tick = 0
    status_byte = 0x90 | (channel & 0x0F)

    for tick, note, velocity, gate in events:
        delta = tick - last_tick
        while delta > 255:
            count = delta // 256
            stream.extend(bytes([0xFE, 0, count, 0, 0, 0]))
            delta %= 256

        gate_lo = gate & 0xFF
        gate_hi = (gate >> 8) & 0xFF
        stream.extend(bytes([status_byte, delta, note, velocity, gate_lo, gate_hi]))
        last_tick = tick

    stream.append(0xFF)
    return bytes(stream)


def _build_bass_stream() -> bytes:
    """Construct Track 1: Smooth Fingerstyle Electric Bass (Channel 1, Program 33)."""
    raw_bass = [
        # Bar 1: Fmaj9 (warm F2 root with melodic walking lines)
        (0, 41, 105, 60),  # F2
        (96, 41, 90, 40),  # F2
        (144, 48, 95, 45),  # C3
        (240, 40, 85, 40),  # E2 (leading tone)
        (288, 41, 105, 60),  # F2
        (336, 43, 90, 40),  # G2 (passing to C)
        # Bar 2: C9sus (C2 root with walking groove)
        (384, 36, 105, 60),  # C2
        (480, 36, 85, 40),  # C2
        (528, 43, 95, 45),  # G2
        (576, 46, 100, 50),  # Bb2
        (624, 48, 95, 40),  # C3
        (672, 50, 90, 40),  # D3
        (720, 40, 95, 40),  # E2 (leading back to F)
        # Bar 3: Fmaj9 (punchy octave pop & turnaround)
        (768, 41, 105, 60),  # F2
        (864, 45, 95, 40),  # A2
        (912, 48, 100, 45),  # C3
        (960, 53, 110, 50),  # F3 (octave accent pop!)
        (1008, 52, 90, 40),  # E3
        (1056, 50, 95, 40),  # D3
        (1104, 48, 90, 40),  # C3
        # Bar 4: C9sus (resolving turnaround)
        (1152, 36, 105, 60),  # C2
        (1248, 43, 90, 40),  # G2
        (1296, 46, 95, 45),  # Bb2
        (1344, 48, 100, 50),  # C3
        (1392, 50, 95, 40),  # D3
        (1440, 40, 100, 40),  # E2
        (1488, 41, 105, 50),  # F2 resolution
    ]
    return _encode_performance_stream(raw_bass, channel=0, program=33)


def _build_guitar_stream() -> bytes:
    """Construct Track 2: Jazz Clean Guitar (Channel 2, Program 26)."""
    # Fmaj9: A3 (57), C4 (60), E4 (64), G4 (67)
    # C9sus: Bb3 (58), D4 (62), F4 (65), G4 (67)
    fmaj9_gtr1 = [57, 60, 64, 67]
    c9sus_gtr1 = [58, 62, 65, 67]
    fmaj9_gtr2 = [57, 64, 67, 72]  # higher C5 extension
    c9sus_gtr2 = [58, 62, 65, 69]  # C13sus (A4)

    raw_gtr_chords: list[tuple[int, int, int, int]] = []
    gtr_chords = [
        (0, fmaj9_gtr1),
        (1, c9sus_gtr1),
        (2, fmaj9_gtr2),
        (3, c9sus_gtr2),
    ]

    for bar, chord in gtr_chords:
        bar_start = bar * BAR
        stabs = [
            (0, 80, 50),  # Beat 1 (downbeat)
            (144, 95, 45),  # Beat 2 & (offbeat stab)
            (336, 90, 50),  # Beat 4 & (syncopated push)
        ]
        for off, vel, gate in stabs:
            t = bar_start + off
            for n in chord:
                raw_gtr_chords.append((t, n, vel, gate))

    # Tasteful guitar turnaround lick at Bar 4 end
    gtr_lick = [
        (3 * BAR + 240, 69, 85, 45),  # A4
        (3 * BAR + 288, 72, 95, 45),  # C5
        (3 * BAR + 336, 74, 95, 55),  # D5
        (3 * BAR + 360, 69, 90, 60),  # A4 resolution
    ]
    raw_gtr_chords.extend(gtr_lick)
    raw_gtr_chords.sort(key=lambda x: x[0])

    return _encode_performance_stream(raw_gtr_chords, channel=1, program=26)


def _build_epiano_stream() -> bytes:
    """Construct Track 3: Electric Piano / Rhodes (Channel 3, Program 4)."""
    ep_chords = [
        # Bar 1 (Fmaj9): F3 (53), A3 (57), C4 (60), E4 (64)
        (0, [53, 57, 60, 64], 75, 340),
        # Bar 2 (C9sus): G3 (55), Bb3 (58), D4 (62), F4 (65)
        (BAR, [55, 58, 62, 65], 75, 340),
        # Bar 3 (Fmaj9): F3 (53), C4 (60), E4 (64), G4 (67)
        (2 * BAR, [53, 60, 64, 67], 78, 340),
        # Bar 4 (C9sus): G3 (55), Bb3 (58), D4 (62), F4 (65)
        (3 * BAR, [55, 58, 62, 65], 80, 340),
    ]

    raw_ep: list[tuple[int, int, int, int]] = []
    for t, chord, vel, gate in ep_chords:
        for n in chord:
            raw_ep.append((t, n, vel, gate))
    raw_ep.sort(key=lambda x: x[0])

    return _encode_performance_stream(raw_ep, channel=2, program=4)


def _build_drum_stream() -> bytes:
    """Construct Slot 12 Pattern 0 drum note stream (3-byte records)."""
    slot12 = bytearray()
    drum_events = [
        # Beat 1 (tick 0): Kick (36) + Closed HH (42)
        (0, 36, 7),
        (0, 42, 5),
        # 8th note (tick 48): Closed HH (42)
        (48, 42, 4),
        # Beat 2 (tick 96): Snare (38) + Closed HH (42)
        (48, 38, 7),
        (0, 42, 5),
        # & of 2 (tick 144): Syncopated Kick (36) + Closed HH (42)
        (48, 36, 6),
        (0, 42, 5),
        # Beat 3 (tick 192): Kick (36) + Closed HH (42)
        (48, 36, 7),
        (0, 42, 5),
        # & of 3 (tick 240): Ghost Snare (38) + Closed HH (42)
        (48, 38, 2),
        (0, 42, 4),
        # Beat 4 (tick 288): Snare (38) + Closed HH (42)
        (48, 38, 7),
        (0, 42, 5),
        # & of 4 (tick 336): Open Hi-Hat (46)
        (48, 46, 6),
    ]
    for dt, note, vc in drum_events:
        slot12.extend(bytes([note, dt, vc]))
    slot12.append(0xFF)
    return bytes(slot12)


def _build_timeline_stream() -> bytes:
    """Construct Slot 2 Measure Arrangement Timeline with dynamic velocity trims."""
    timeline = bytearray()
    for trim_val in [0, 4, 8, 2]:
        trim_byte = trim_val if trim_val >= 0 else (256 + trim_val)
        timeline.extend(bytes([0, 0, trim_byte]))
    timeline.append(0xFF)
    return bytes(timeline)


def _write_24bit_le(buf: bytearray, offset: int, value: int) -> None:
    """Write a 24-bit unsigned integer in little-endian order."""
    buf[offset] = value & 0xFF
    buf[offset + 1] = (value >> 8) & 0xFF
    buf[offset + 2] = (value >> 16) & 0xFF


def _write_track_descriptor(
    buf: bytearray, track_index: int, start_offset: int, byte_length: int
) -> None:
    """Write a 16-byte performance track descriptor starting at 0x0040."""
    slot_offset = 0x0040 + (track_index * 16)
    _write_24bit_le(buf, slot_offset, start_offset)
    _write_24bit_le(buf, slot_offset + 3, byte_length)


def _assemble_sng_binary(
    trk1_stream: bytes,
    trk2_stream: bytes,
    trk3_stream: bytes,
    slot12_stream: bytes,
    slot2_stream: bytes,
) -> bytes:
    """Assemble individual streams into a valid Super-MRC binary image."""
    header_len = 0x300
    slot2_off = header_len
    slot12_off = slot2_off + len(slot2_stream)
    trk1_off = slot12_off + len(slot12_stream)
    trk2_off = trk1_off + len(trk1_stream)
    trk3_off = trk2_off + len(trk2_stream)
    total_len = trk3_off + len(trk3_stream)

    buf = bytearray(total_len)

    # Song title and global pointers
    buf[0:16] = b"FMAJ9 C9SUS GROV"
    _write_24bit_le(buf, 0x0010, total_len)
    _write_24bit_le(buf, 0x0020, slot2_off)

    # Track descriptors 1-3
    _write_track_descriptor(buf, 0, trk1_off, len(trk1_stream))
    _write_track_descriptor(buf, 1, trk2_off, len(trk2_stream))
    _write_track_descriptor(buf, 2, trk3_off, len(trk3_stream))

    # Rhythm slot 12 pointer and initial tempo
    _write_24bit_le(buf, 0x00C0, slot12_off)
    buf[0x00F1] = 110  # 110 BPM

    # Pattern 0 descriptor at 0x02A0 (22 bytes)
    buf[0x02A0] = 0  # pattern index 0
    buf[0x02A1] = 0  # slot12 relative offset 0
    buf[0x02A2] = 0
    buf[0x02A5] = 4  # 4 beats per bar

    # Write streams into buffer
    buf[slot2_off : slot2_off + len(slot2_stream)] = slot2_stream
    buf[slot12_off : slot12_off + len(slot12_stream)] = slot12_stream
    buf[trk1_off : trk1_off + len(trk1_stream)] = trk1_stream
    buf[trk2_off : trk2_off + len(trk2_stream)] = trk2_stream
    buf[trk3_off : trk3_off + len(trk3_stream)] = trk3_stream

    return bytes(buf)


def build_demo_sng() -> bytes:
    """Build an authentic multi-track Super-MRC song binary in Fmaj9 <-> C9sus."""
    trk1_stream = _build_bass_stream()
    trk2_stream = _build_guitar_stream()
    trk3_stream = _build_epiano_stream()
    slot12_stream = _build_drum_stream()
    slot2_stream = _build_timeline_stream()

    return _assemble_sng_binary(
        trk1_stream=trk1_stream,
        trk2_stream=trk2_stream,
        trk3_stream=trk3_stream,
        slot12_stream=slot12_stream,
        slot2_stream=slot2_stream,
    )


def build_floppy_catalog(song_title: str, stem: str) -> bytes:
    """Build a minimal MC500DIR.TNB catalog file."""
    buf = bytearray(0x0200)
    buf[0x0100] = 0x80  # valid entry marker
    title_bytes = song_title.encode("ascii")[:16].ljust(16, b" ")
    buf[0x0101:0x0111] = title_bytes
    stem_bytes = stem.encode("ascii")[:8].ljust(8, b" ")
    buf[0x0110:0x0118] = stem_bytes
    buf[0x0118:0x011B] = b"SNG"
    return bytes(buf)


def main() -> None:
    examples_dir = Path("examples")
    examples_dir.mkdir(exist_ok=True)

    # 1. Standalone demo file
    demo_sng_path = examples_dir / "demo.sng"
    demo_bytes = build_demo_sng()
    demo_sng_path.write_bytes(demo_bytes)
    print(f"Generated {demo_sng_path} ({len(demo_bytes)} bytes)")

    # Validate parsing
    song = parse_sng_file(demo_sng_path)
    print(
        f"Validated {song.title}: {song.initial_tempo_bpm} BPM, "
        f"{len(song.performance_tracks)} tracks, {len(song.rhythm_events)} drum events"
    )

    # 2. Floppy sample folder
    floppy_dir = examples_dir / "floppy_sample"
    floppy_dir.mkdir(exist_ok=True)
    catalog_bytes = build_floppy_catalog("FMAJ9 C9SUS GROV", "TNB00000")
    (floppy_dir / "MC500DIR.TNB").write_bytes(catalog_bytes)
    (floppy_dir / "TNB00000.SNG").write_bytes(demo_bytes)
    print(f"Generated floppy sample in {floppy_dir}")


if __name__ == "__main__":
    main()
