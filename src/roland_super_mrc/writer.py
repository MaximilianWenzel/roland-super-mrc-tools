"""Standard MIDI File (SMF) serializer for Roland Super-MRC songs.

Uses mido to emit bit-accurate SMF Format 1 and Format 0 files with
tempo maps, metadata, and separate performance/rhythm tracks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import mido  # type: ignore

from roland_super_mrc.models import SuperMrcSong, TimedMidiEvent


def _event_to_mido_message(
    ev: TimedMidiEvent,
    default_channel: int | None = None,
) -> tuple[int, mido.Message] | None:
    """Convert TimedMidiEvent to a priority-tagged mido.Message."""
    ch = ev.channel if default_channel is None else default_channel
    status_type = ev.status & 0xF0

    if status_type == 0x80:
        return (1, mido.Message("note_off", channel=ch, note=ev.data1, velocity=ev.data2))
    if status_type == 0x90:
        if ev.data2 == 0:
            return (1, mido.Message("note_off", channel=ch, note=ev.data1, velocity=64))
        return (4, mido.Message("note_on", channel=ch, note=ev.data1, velocity=ev.data2))
    if status_type == 0xC0:
        return (2, mido.Message("program_change", channel=ch, program=ev.data1))
    if status_type == 0xB0:
        return (3, mido.Message("control_change", channel=ch, control=ev.data1, value=ev.data2))
    if status_type == 0xE0:
        bend_val = (ev.data1 | (ev.data2 << 7)) - 8192
        return (3, mido.Message("pitchwheel", channel=ch, pitch=bend_val))
    return None


def build_midi_track(
    name: str,
    events: Sequence[TimedMidiEvent],
    default_channel: int | None = None,
) -> mido.MidiTrack:
    """Construct and serialize a single mido.MidiTrack from absolute tick events."""
    track = mido.MidiTrack()
    if name:
        track.append(mido.MetaMessage("track_name", name=name, time=0))

    if not events:
        track.append(mido.MetaMessage("end_of_track", time=0))
        return track

    # Priority tuple: (tick, priority, stable_index, event_object)
    # Priority order: Meta(0) < Note-Off(1) < Program-Change(2) < Control-Change(3) < Note-On(4)
    staged: list[tuple[int, int, int, mido.Message]] = []

    for idx, ev in enumerate(events):
        res = _event_to_mido_message(ev, default_channel=default_channel)
        if res is not None:
            prio, msg = res
            staged.append((ev.tick, prio, idx, msg))

    staged.sort(key=lambda x: (x[0], x[1], x[2]))

    last_tick = 0
    for tick, _, _, msg in staged:
        delta = max(0, tick - last_tick)
        msg.time = delta
        track.append(msg)
        last_tick = tick

    track.append(mido.MetaMessage("end_of_track", time=0))
    return track


def _serialize_format_0(song: SuperMrcSong) -> mido.MidiFile:
    """Merge conductor metadata, performance events, and rhythm into a single track chunk."""
    mid = mido.MidiFile(type=0, ticks_per_beat=song.ppqn)
    staged_all: list[tuple[int, int, int, mido.Message]] = []
    seq = 0

    title = song.title if song.title else "Super-MRC"
    staged_all.append((0, 0, seq, mido.MetaMessage("track_name", name=title, time=0)))
    seq += 1
    staged_all.append(
        (
            0,
            0,
            seq,
            mido.MetaMessage(
                "time_signature",
                numerator=song.time_signature[0],
                denominator=song.time_signature[1],
                time=0,
            ),
        )
    )
    seq += 1
    staged_all.append(
        (
            0,
            0,
            seq,
            mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(song.initial_tempo_bpm), time=0),
        )
    )
    seq += 1

    for tempo_ev in song.tempo_changes:
        if tempo_ev.tick == 0 and round(tempo_ev.bpm) == song.initial_tempo_bpm:
            continue
        staged_all.append(
            (
                tempo_ev.tick,
                0,
                seq,
                mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_ev.bpm), time=0),
            )
        )
        seq += 1

    for trk in song.performance_tracks:
        for ev in trk.events:
            res = _event_to_mido_message(ev)
            if res is not None:
                prio, msg = res
                staged_all.append((ev.tick, prio, seq, msg))
                seq += 1

    for ev in song.rhythm_events:
        res = _event_to_mido_message(ev)
        if res is not None:
            prio, msg = res
            staged_all.append((ev.tick, prio, seq, msg))
            seq += 1

    staged_all.sort(key=lambda x: (x[0], x[1], x[2]))

    unified_track = mido.MidiTrack()
    last_tick = 0
    for tick, _, _, msg in staged_all:
        delta = max(0, tick - last_tick)
        msg.time = delta
        unified_track.append(msg)
        last_tick = tick

    unified_track.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(unified_track)
    return mid


def _serialize_format_1(song: SuperMrcSong) -> mido.MidiFile:
    """Serialize as SMF Format 1: Conductor Track + Individual Performance Tracks + Rhythm Track."""
    mid = mido.MidiFile(type=1, ticks_per_beat=song.ppqn)
    conductor = mido.MidiTrack()
    conductor.append(mido.MetaMessage("track_name", name=song.title or "Conductor", time=0))

    initial_tempo_us = mido.bpm2tempo(song.initial_tempo_bpm)
    conductor.append(mido.MetaMessage("set_tempo", tempo=initial_tempo_us, time=0))
    conductor.append(
        mido.MetaMessage(
            "time_signature",
            numerator=song.time_signature[0],
            denominator=song.time_signature[1],
            time=0,
        )
    )

    last_tick = 0
    for tempo_ev in song.tempo_changes:
        if tempo_ev.tick == 0 and round(tempo_ev.bpm) == song.initial_tempo_bpm:
            continue
        delta = max(0, tempo_ev.tick - last_tick)
        tempo_us = mido.bpm2tempo(tempo_ev.bpm)
        conductor.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=delta))
        last_tick = tempo_ev.tick

    conductor.append(mido.MetaMessage("end_of_track", time=0))
    mid.tracks.append(conductor)

    for trk in song.performance_tracks:
        midi_trk = build_midi_track(trk.name, trk.events)
        mid.tracks.append(midi_trk)

    if song.rhythm_events:
        rhythm_trk = build_midi_track("Rhythm (Channel 10)", song.rhythm_events)
        mid.tracks.append(rhythm_trk)

    return mid


def serialize_to_midi(
    song: SuperMrcSong,
    format_type: int = 1,
) -> mido.MidiFile:
    """Convert a SuperMrcSong model into a mido.MidiFile."""
    if format_type == 0:
        return _serialize_format_0(song)
    return _serialize_format_1(song)


def write_midi_file(
    song: SuperMrcSong,
    output_path: Path,
    format_type: int = 1,
) -> Path:
    """Serialize and write a SuperMrcSong to disk as a Standard MIDI File."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mid = serialize_to_midi(song, format_type=format_type)
    mid.save(str(output_path))
    return output_path
