"""Domain entities and value objects for Roland Super-MRC.

All entities are immutable, slotted dataclasses representing songs,
tracks, events, and rhythm arrangements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Sequence


class NamingMode(StrEnum):
    """Output filename formatting mode for converted MIDI files."""

    INDEX_TITLE = "index-title"
    TITLE = "title"
    ORIGINAL = "original"


class MidiStatus(IntEnum):
    """MIDI status byte upper nibble identifiers."""

    NOTE_OFF = 0x80
    NOTE_ON = 0x90
    POLY_PRESSURE = 0xA0
    CONTROL_CHANGE = 0xB0
    PROGRAM_CHANGE = 0xC0
    CHANNEL_PRESSURE = 0xD0
    PITCH_BEND = 0xE0
    TIMING_SKIP = 0xFE
    END_OF_TRACK = 0xFF


@dataclass(frozen=True, slots=True)
class TimedMidiEvent:
    """A deterministic MIDI event scheduled at an absolute PPQN tick."""

    tick: int
    status: int
    channel: int
    data1: int
    data2: int = 0
    gate_ticks: int = 0


@dataclass(frozen=True, slots=True)
class TrackDescriptor:
    """Metadata pointing to an 8-track performance stream slot."""

    track_index: int  # 0 to 7 (corresponds to physical tracks 1 to 8)
    start_offset: int
    byte_length: int


@dataclass(frozen=True, slots=True)
class PatternDescriptor:
    """Header record for a 22-byte rhythm pattern stored at 0x02A0."""

    pattern_index: int
    relative_offset: int
    beats_per_measure: int


@dataclass(frozen=True, slots=True)
class RhythmPatternNote:
    """A drum note event inside a rhythm pattern."""

    rel_tick: int
    note: int
    vel_code: int


@dataclass(frozen=True, slots=True)
class DecodedPattern:
    """Decoded rhythm pattern containing RhythmPatternNote items."""

    pattern_index: int
    beats: int
    notes: tuple[RhythmPatternNote, ...]


@dataclass(frozen=True, slots=True)
class MeasureTimelineEntry:
    """3-byte arrangement entry stored at Slot 2 pointer (0x0020)."""

    measure_index: int
    pattern_slot: int  # Physical index into pattern table (0xF4=rest, 0xFF=end)
    velocity_trim: int  # Signed 8-bit trim (-128 to +127)


@dataclass(frozen=True, slots=True)
class TempoEvent:
    """Tempo change event stored in the conductor track at 0x0030."""

    tick: int
    bpm: float


@dataclass(frozen=True, slots=True)
class PerformanceTrack:
    """A decoded performance track (Tracks 1 to 8)."""

    track_number: int  # 1 to 8
    name: str
    events: Sequence[TimedMidiEvent] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SuperMrcSong:
    """Complete decoded Roland MC-50 / Super-MRC song structure."""

    title: str
    initial_tempo_bpm: int
    time_signature: tuple[int, int]
    ppqn: int = 96
    performance_tracks: Sequence[PerformanceTrack] = field(default_factory=tuple)
    rhythm_events: Sequence[TimedMidiEvent] = field(default_factory=tuple)
    tempo_changes: Sequence[TempoEvent] = field(default_factory=tuple)
    measure_count: int = 0
