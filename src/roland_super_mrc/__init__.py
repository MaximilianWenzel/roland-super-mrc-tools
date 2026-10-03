"""Roland Super-MRC Tools.

Bit-accurate binary parser and Standard MIDI converter for Roland MC-50,
MC-50mkII, and MC-500 Super-MRC (.SNG) files.
"""

from roland_super_mrc.exceptions import (
    CorruptHeaderError,
    InvalidOpcodeError,
    RhythmParseError,
    SuperMrcError,
    TrackParseError,
)
from roland_super_mrc.catalog import (
    parse_mc500_directory,
    resolve_output_filename,
    sanitize_filename,
)
from roland_super_mrc.models import (
    DecodedPattern,
    MeasureTimelineEntry,
    NamingMode,
    PatternDescriptor,
    PerformanceTrack,
    RhythmPatternNote,
    SuperMrcSong,
    TempoEvent,
    TimedMidiEvent,
    TrackDescriptor,
)
from roland_super_mrc.parser import parse_sng_bytes, parse_sng_file
from roland_super_mrc.rhythm import decode_rhythm_stream, parse_drum_palette
from roland_super_mrc.writer import serialize_to_midi, write_midi_file

__version__ = "1.0.0"

__all__ = [
    "CorruptHeaderError",
    "DecodedPattern",
    "InvalidOpcodeError",
    "MeasureTimelineEntry",
    "NamingMode",
    "PatternDescriptor",
    "PerformanceTrack",
    "RhythmParseError",
    "RhythmPatternNote",
    "SuperMrcError",
    "SuperMrcSong",
    "TempoEvent",
    "TimedMidiEvent",
    "TrackDescriptor",
    "TrackParseError",
    "decode_rhythm_stream",
    "parse_drum_palette",
    "parse_mc500_directory",
    "parse_sng_bytes",
    "parse_sng_file",
    "resolve_output_filename",
    "sanitize_filename",
    "serialize_to_midi",
    "write_midi_file",
]
