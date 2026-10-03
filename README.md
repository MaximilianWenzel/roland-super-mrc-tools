# roland-super-mrc-tools

Bit-accurate parser, converter, and inspection toolkit for proprietary Roland Super-MRC song files (`.SNG`) created on **Roland MC-50**, **MC-50mkII**, and **MC-500** hardware MIDI sequencers.

Converts raw binary `.SNG` floppy disk files into standard SMF Format 1 or Format 0 MIDI files, reproducing melodic performance tracks, dynamic tempo maps, and unrolled Channel 10 rhythm arrangements note-for-note.

---

## Quick Start

### Installation

**Option 1: Standalone Executable (Recommended — No Python required)**

Download the pre-compiled binary for your OS from [Releases](https://github.com/MaximilianWenzel/roland-super-mrc-tools/releases):
- **Windows:** Run `.\sng2mid.exe` from PowerShell or Command Prompt.
- **macOS / Linux:** Make it executable (`chmod +x sng2mid`) and run `./sng2mid`.

**Option 2: From Source (Python 3.11+)**

```bash
git clone https://github.com/MaximilianWenzel/roland-super-mrc-tools.git
cd roland-super-mrc-tools
poetry install
```
*(When running from a source checkout, prefix commands with `poetry run sng2mid`)*

### Convert a File

```bash
# Convert a single song to SMF Format 1 (multi-track)
sng2mid convert song.sng -o song.mid

# Convert with verbose track inspection
sng2mid convert song.sng -v

# Convert to SMF Format 0 (single unified track)
sng2mid convert song.sng -f 0
```

### Inspect Binary Metadata

Display internal headers, measure counts, tempo maps, and track structures without writing a file:

```bash
sng2mid inspect song.sng
```

### Batch Convert a Folder

Convert an entire directory tree of floppy disk archives:

```bash
sng2mid batch /path/to/floppies -o /path/to/midi --recursive
```

---

## Python Library Usage

The package exposes high-level parsing and conversion functions:

```python
from pathlib import Path
from roland_super_mrc import parse_sng_file, write_midi_file

# Parse raw binary SNG into an immutable SuperMrcSong model
song = parse_sng_file(Path("AUTUMN.SNG"))

print(f"Title: {song.title}")
print(f"Tempo: {song.initial_tempo_bpm} BPM ({song.time_signature[0]}/{song.time_signature[1]})")
print(f"Performance Tracks: {len(song.performance_tracks)}")
print(f"Rhythm Measures: {song.measure_count} ({len(song.rhythm_events)} drum events)")

# Export to Standard MIDI Format 1
write_midi_file(song, Path("AUTUMN.mid"), format_type=1)
```

---

## Format Documentation

Super-MRC (`.SNG`) sequences use 24-bit little-endian pointers, a fixed 96 PPQN timebase, and separate linear performance tracks from a pattern-based drum arrangement engine.

Detailed specifications and architectural guides are available in `docs/`:

- **[Binary Format Specification](docs/format-specification.md):** Byte-level layout covering disk directory catalogs (`MC500DIR.TNB`), header offsets, 6-byte performance event records, 3-byte rhythm timeline entries, and 24-bit stream pointers.
- **[Internals & Architecture](docs/internals.md):** Hardware constraints (static RAM budget, 720 KB floppies), 96 PPQN timing math, the dual tape/drum sequencer engine, signed velocity trimming, and SMF zero-tick note collision resolution.

---

## Fidelity & Limitations

This converter was built through reverse engineering of Roland MC-50 floppy disk dumps and validated against original Roland hardware SMF exports.

### Supported Features
- Tracks 1–8 performance streams (notes, gate times, pitch bend, control change, program change, aftertouch).
- Tempo conductor track with initial tempo and dynamic tempo/meter changes.
- Unrolled Channel 10 rhythm timelines, including signed measure velocity trims and pattern rest measures.
- Floppy disk catalog parsing (`MC500DIR.TNB`) for automated song title resolution.
- SMF Format 1 (multi-track) and Format 0 (single unified track) export.

### Known Boundaries
- **Proprietary Hardware SysEx:** Roland hardware sequencer setup dumps or micro-edit parameters embedded inside performance tracks are currently skipped.
- **Sparse Pattern Boundaries:** In sparse `.SNG` files where performance tracks begin immediately after the pattern table (e.g. `0x02B8`), the parser safely bounds descriptor iteration to prevent reading melodic notes as phantom drum patterns. Undefined pattern references fall back to an empty 4/4 bar.

If you encounter an `.SNG` file that fails to parse or produces unexpected playback, please open an issue with a sample file or hex dump.

---

## Project Origin & Methodology

This project was developed through human-agent pair programming using Google DeepMind's Antigravity coding tools.

Because proprietary binary formats require precise handling of edge cases, conversion fidelity is verified through automated test suites:
- Unit tests covering binary edge cases (timing skips, signed velocity trims, rest bars, and variable tempos).
- Comparison against native Roland MC-50 hardware SMF disk exports.
- Strict static type checking (`mypy --strict`) and automated linting (`ruff`).
- Pre-commit automated quality gates enforcing formatting, linting, and tests.

---

## Project Architecture

```text
roland-super-mrc-tools/
├── docs/
│   ├── format-specification.md  # Complete byte-level Super-MRC reference
│   └── internals.md             # Hardware context, timing math & architectural deep dive
├── src/roland_super_mrc/
│   ├── catalog.py       # MC500DIR.TNB directory parser & filename sanitization
│   ├── parser.py        # Binary decoder for Super-MRC streams
│   ├── models.py        # Domain entities (SuperMrcSong, TimedMidiEvent, NamingMode)
│   ├── rhythm.py        # Rhythm pattern unpacker & velocity trim unroller
│   ├── writer.py        # SMF Format 1 & 0 serializer (via mido)
│   └── cli.py           # Typer CLI entry point (sng2mid)
└── tests/
```

- **Bit-Accurate:** Synthetic binary test fixtures verify byte-for-byte fidelity against original hardware ROM outputs.
- **Standalone:** No external DAW or proprietary runtime dependencies; converts directly to standard SMF.

---

## Testing & Quality

Run the test suite:

```bash
poetry run pytest
```

Run static type checking in strict mode:

```bash
poetry run mypy src tests
```

Run linter and formatter:

```bash
poetry run ruff check src tests
poetry run ruff format --check src tests
```

Install local pre-commit hooks:

```bash
poetry run pre-commit install
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.

