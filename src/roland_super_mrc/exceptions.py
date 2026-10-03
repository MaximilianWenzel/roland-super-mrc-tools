"""Domain exceptions for Roland Super-MRC processing."""

from __future__ import annotations


class SuperMrcError(Exception):
    """Base exception for all Roland Super-MRC operations."""


class CorruptHeaderError(SuperMrcError):
    """Raised when an SNG binary file header is missing, too short, or malformed."""


class TrackParseError(SuperMrcError):
    """Raised when an SNG performance track contains invalid offsets or corrupt byte streams."""


class RhythmParseError(SuperMrcError):
    """Raised when rhythm pattern descriptors or measure timelines cannot be decoded."""


class InvalidOpcodeError(SuperMrcError):
    """Raised when encountering an illegal or unsupported Super-MRC binary opcode."""
