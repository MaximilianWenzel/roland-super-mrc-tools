"""Tests for Standard MIDI File (SMF) serialization and disk I/O."""

from __future__ import annotations

from pathlib import Path

import mido  # type: ignore

from roland_super_mrc.models import (
    MidiStatus,
    PerformanceTrack,
    SuperMrcSong,
    TempoEvent,
    TimedMidiEvent,
)
from roland_super_mrc.writer import build_midi_track, serialize_to_midi, write_midi_file


def _build_test_song() -> SuperMrcSong:
    """Helper to assemble a valid, multi-track SuperMrcSong domain model."""
    events_trk1 = (
        TimedMidiEvent(tick=0, status=MidiStatus.NOTE_ON.value, channel=0, data1=60, data2=100),
        TimedMidiEvent(tick=96, status=MidiStatus.NOTE_OFF.value, channel=0, data1=60, data2=64),
        TimedMidiEvent(tick=96, status=MidiStatus.NOTE_ON.value, channel=0, data1=64, data2=90),
        TimedMidiEvent(tick=192, status=MidiStatus.NOTE_OFF.value, channel=0, data1=64, data2=64),
    )
    trk1 = PerformanceTrack(track_number=1, name="Piano Comping", events=events_trk1)

    rhythm_events = (
        TimedMidiEvent(tick=0, status=MidiStatus.NOTE_ON.value, channel=9, data1=36, data2=100),
        TimedMidiEvent(tick=24, status=MidiStatus.NOTE_OFF.value, channel=9, data1=36, data2=64),
        TimedMidiEvent(tick=96, status=MidiStatus.NOTE_ON.value, channel=9, data1=38, data2=95),
        TimedMidiEvent(tick=120, status=MidiStatus.NOTE_OFF.value, channel=9, data1=38, data2=64),
    )

    tempo_changes = (
        TempoEvent(tick=0, bpm=120.0),
        TempoEvent(tick=192, bpm=130.0),
    )

    return SuperMrcSong(
        title="JAZZ NOCTURNE",
        ppqn=96,
        initial_tempo_bpm=120,
        time_signature=(4, 4),
        performance_tracks=(trk1,),
        rhythm_events=rhythm_events,
        tempo_changes=tempo_changes,
    )


def test_build_midi_track_delta_times() -> None:
    """Verify that build_midi_track computes relative delta times accurately."""
    events = (
        TimedMidiEvent(tick=0, status=MidiStatus.NOTE_ON.value, channel=0, data1=60, data2=100),
        TimedMidiEvent(tick=48, status=MidiStatus.NOTE_OFF.value, channel=0, data1=60, data2=64),
        TimedMidiEvent(tick=96, status=MidiStatus.NOTE_ON.value, channel=0, data1=62, data2=100),
    )
    track = build_midi_track(name="Lead Track", events=events)

    # 1 meta track_name + 3 channel messages + 1 meta end_of_track = 5
    assert len(track) == 5
    assert track[0].type == "track_name"
    assert track[0].name == "Lead Track"
    assert track[1].type == "note_on"
    assert track[1].time == 0
    assert track[2].type == "note_off"
    assert track[2].time == 48
    assert track[3].type == "note_on"
    assert track[3].time == 48  # 96 - 48
    assert track[4].type == "end_of_track"
    assert track[4].time == 0


def test_serialize_format_1() -> None:
    """Verify SMF Format 1 serialization with conductor, performance, and rhythm tracks."""
    song = _build_test_song()
    mid = serialize_to_midi(song, format_type=1)

    assert mid.type == 1
    assert mid.ticks_per_beat == 96
    assert len(mid.tracks) == 3  # Conductor + Track 1 + Rhythm Track

    # Conductor track assertions
    conductor = mid.tracks[0]
    meta_types = [msg.type for msg in conductor]
    assert "track_name" in meta_types
    assert "time_signature" in meta_types
    assert "set_tempo" in meta_types
    assert meta_types[-1] == "end_of_track"

    # Track 1 assertions
    trk1 = mid.tracks[1]
    assert trk1[0].name == "Piano Comping"
    note_events = [msg for msg in trk1 if msg.type in ("note_on", "note_off")]
    assert len(note_events) == 4

    # Rhythm track assertions (Channel 10 = channel 9 in 0-indexed MIDI)
    rhythm_trk = mid.tracks[2]
    assert rhythm_trk[0].name == "Rhythm (Channel 10)"
    rhythm_notes = [msg for msg in rhythm_trk if msg.type in ("note_on", "note_off")]
    assert len(rhythm_notes) == 4
    for msg in rhythm_notes:
        assert msg.channel == 9


def test_serialize_format_0() -> None:
    """Verify SMF Format 0 serialization with unified, interleaved track chunk."""
    song = _build_test_song()
    mid = serialize_to_midi(song, format_type=0)

    assert mid.type == 0
    assert mid.ticks_per_beat == 96
    assert len(mid.tracks) == 1

    track = mid.tracks[0]
    # Check that there is only one end_of_track and it is at the very end
    end_of_track_count = sum(1 for msg in track if msg.type == "end_of_track")
    assert end_of_track_count == 1
    assert track[-1].type == "end_of_track"

    # Verify chronological ordering (cumulative ticks never decrease)
    current_tick = 0
    for msg in track:
        assert msg.time >= 0
        current_tick += msg.time

    # Should contain both channel 0 and channel 9 note events
    channels = {msg.channel for msg in track if msg.type in ("note_on", "note_off")}
    assert channels == {0, 9}


def test_write_midi_file_disk_io(tmp_path: Path) -> None:
    """Verify that write_midi_file writes an authentic SMF file readable by standard parsers."""
    song = _build_test_song()
    out_file = tmp_path / "subdir" / "test_export.mid"

    result_path = write_midi_file(song, out_file, format_type=1)

    assert result_path.exists()
    assert result_path.stat().st_size > 0

    # Re-parse with mido from disk
    parsed_mid = mido.MidiFile(str(result_path))
    assert parsed_mid.type == 1
    assert parsed_mid.ticks_per_beat == 96
    assert len(parsed_mid.tracks) == 3
