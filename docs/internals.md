# Roland Super-MRC Internals & Architecture

> **Status: Empirical Architecture & Implementation Notes**  
> This document records architectural observations and conversion mechanics derived from reverse-engineering Roland MC-50 sequence files. It focuses on the subset of behaviors required to reconstruct faithful MIDI files and resolve timing quirks.

---

## Hardware Context (1988–1992)

The Roland MC-50 was a dedicated hardware sequencer powered by a vintage microprocessor running proprietary Roland OS firmware. Because the unit had to run without an operating system layer or hard disk drive, its data structures were tailored to two physical constraints:

1. **RAM Budget:** Sequence memory maxed out at approximately 40,000 notes in static RAM. Data records had to be packed into compact fixed-width bitfields (such as 6-byte performance tuples and 3-byte rhythm notes).
2. **Floppy Disk Subsystem:** Sequences were stored on 3.5" double-density (2DD, 720 KB) floppy disks. Rather than implementing a full PC-compatible FAT12 filesystem, Roland partitioned disks with a proprietary catalog file named `MC500DIR.TNB` starting at offset `0x0100`, indexing song stems like `TNB00000.SNG`.

---

## Why 96 PPQN?

Super-MRC sequences run at a fixed resolution of **96 pulses per quarter note (PPQN)**. At first glance, modern DAWs operate at 480, 960, or higher PPQN. 96 was chosen in hardware for integer divisibility:

```text
Quarter note:     96 ticks
Eighth note:      48 ticks
Eighth triplet:   32 ticks  (96 / 3)
Sixteenth note:   24 ticks  (96 / 4)
Sixteenth triplet:16 ticks  (96 / 6)
Thirty-second:    12 ticks  (96 / 8)
Thirty-second trip:8 ticks  (96 / 12)
Sixty-fourth:      6 ticks  (96 / 16)
```

Because 96 is divisible by 2, 3, 4, 6, 8, 12, 16, 24, 32, and 48, vintage microprocessors could schedule straight, dotted, and triplet figures across all standard musical meters using single-cycle integer arithmetic, avoiding fractional rounding errors.

---

## Dual Sequencing Paradigms: Tape vs. Pattern Arranger

Roland Super-MRC operates on two completely different sequencing paradigms simultaneously:

### Performance Tracks 1–8: Linear MIDI Tape
Tracks 1 through 8 behave like a digital 8-track tape recorder. Performance events (pitches, velocities, aftertouch, control changes, and pitch bend) are stored linearly as 6-byte records. Timing advances strictly via 1-byte delta ticks, using `0xFE` timing skip opcodes when pauses exceed 255 ticks:

```python
# 0xFE timing skip
current_tick += delta + (count * 256)
```

### Rhythm Track: Pattern-Based Drum Arranger
Rhythm is not recorded linearly. Roland sequencers featured a dedicated drum machine workflow (analogous to the Roland R-8 or TR-series drum machines):
- **Pattern Bank (Slot 12, `0x00C0`):** Individual reusable drum patterns (e.g. Intro, Verse 1, Fill A) stored as 3-byte tuples `[SoundIndex, DeltaTick, VelocityCode]`.
- **Pattern Table (`0x02A0`):** 22-byte descriptors defining the length (in beats) and relative offset into Slot 12.
- **Measure Timeline (Slot 2, `0x0020`):** A sequence of 3-byte records `[PatternIndex, Reserved, VelocityTrim]` terminated by `0xFF`.

When exporting to Standard MIDI, the rhythm engine unrolls the timeline into an absolute, linear event stream assigned to MIDI Channel 10.

---

## Dynamic Velocity Trims in the Rhythm Engine

A distinctive feature of Roland Super-MRC is the **signed 8-bit velocity trim** applied to each measure in Slot 2.

The 3rd byte of each 3-byte timeline entry (detailed in [docs/format-specification.md](format-specification.md#measure-arrangement-timeline-slot-2-0x0020)) is decoded as a two's-complement signed 8-bit integer:

```python
trim = data[offset + 2]
signed_trim = trim if trim < 128 else (trim - 256)
```

Musicians used this to program crescendos, decrescendos, and accents across a song without creating duplicate patterns. If Verse 1 used Pattern 4 at base velocity and the Chorus repeated Pattern 4 with `Velocity Trim = +12`, every drum hit in that chorus measure was shifted louder while retaining pattern micro-dynamics.

Velocity codes (`0` to `7`) map to an 8-level velocity table, combined additively with the trim and clamped to standard MIDI bounds:

```python
if vel_code == 7 or vel_code >= len(vel_table):
    base_velocity = 127
else:
    base_velocity = vel_table[vel_code]

effective_velocity = max(1, min(127, base_velocity + signed_trim))
```

---

## 16-Bit Gate Times vs. Discrete Note-Off Events

In Standard MIDI Files (SMF), notes are formed by separate `note_on` and `note_off` (or `note_on` with velocity 0) messages separated by delta time.

In Super-MRC, performance notes are recorded with an integrated **16-bit gate time** rather than discrete Note-Off messages (see [docs/format-specification.md](format-specification.md#performance-event-stream-format)):

```python
gate_ticks = gate_low | (gate_high << 8)
note_off_tick = current_tick + gate_ticks
```

This saved sequence RAM on the hardware sequencer. However, when converting to SMF, overlapping gates or zero-tick collisions can cause playback anomalies in modern DAWs if not prioritized correctly.

### Zero-Tick Collision Resolution
If a Note-Off occurs at the exact same tick as a Note-On on the same pitch, standard MIDI parsers can cancel the note immediately if Note-On is processed before Note-Off.

To guarantee bit-accurate playback, the serializer in `writer.py` sorts staged messages by a deterministic priority tuple before computing relative delta times:

```python
# Priority order: Meta(0) < Note-Off(1) < Program-Change(2) < Control-Change(3) < Note-On(4)
staged.sort(key=lambda item: (item.tick, item.priority, item.stable_index))
```

By guaranteeing that `Note-Off (priority 1)` is emitted before `Note-On (priority 4)` at any identical tick, polyphonic voice re-triggering functions correctly in all modern DAWs and virtual instruments.

---

## Conductor Track & Fixed-Point Tempo Curves (`0xF9`)

Dynamic tempo variations are recorded in the Conductor Track (Slot 3, `0x0030`) using opcode `0xF9` (detailed in [docs/format-specification.md](format-specification.md#conductor-stream-format-slot-3-0x0030)).

Bytes 2 and 3 store a 16-bit little-endian **8.8 fixed-point ratio** (`w1`), where `256 = 1.0x` initial tempo:

```python
w1 = data[offset + 2] | (data[offset + 3] << 8)
if w1 > 0:
    tempo_bpm = max(20.0, min(350.0, round(initial_tempo_bpm * (w1 / 256.0))))
```

This proportional representation allowed Roland sequencers to perform smooth accelerando and ritardando sweeps relative to whatever base tempo the song was assigned.

---

## Roland Drum Note Index Remapping

In raw Roland MC-50 files, drum patterns occasionally reference internal sound indices that do not correspond to General MIDI (GM) drum note numbers:
- Sound index `3`: Roland internal Bass Drum 1 $\to$ remapped to GM note `36` (Bass Drum 1).
- Sound index `118`: Roland internal Low Tom $\to$ remapped to GM note `41` (Low Floor Tom).

Without this remapping, converted MIDI files trigger silent or unmapped notes on standard GM sound modules and DAW drum samplers. When an embedded drum palette is present at `0x0130`, custom user sound maps override the defaults.

---

## Verification Methodology & Hardware Parity

Because proprietary binary reverse engineering is prone to subtle alignment errors, the algorithms in this repository were verified through two independent parity pipelines:

1. **Synthetic Binary Test Suite:** Deterministic unit tests in `tests/` construct binary chunks from raw byte primitives to test timing edge cases (`0xFE` 256-tick skips, signed velocity trimming, rest measures, fixed-point tempos, and gate durations).
2. **Hardware Parity:** Output was verified against native Roland MC-50 hardware SMF disk exports. Extracted pitches, tick positions, channels, and velocities match the Roland hardware exports bit-for-bit.

---

## Known Boundaries & Edge Cases

When converting vintage floppy dumps, keep the following hardware boundaries in mind:

- **Hardware SysEx Dumps:** Roland MC-50 micro-edit setup messages and hardware bulk dumps embedded inside tracks are skipped.
- **Voice Stealing on Monophonic Tracks:** Hardware Roland sequencers handled voice allocation on vintage sound modules (like the Roland Sound Canvas SC-55 or MT-32). If a performance track contains overlapping identical notes without an intervening Note-Off, polyphonic voice behavior depends on the receiving synth.
- **Sparse File Boundary Clamping:** In sparse songs where Track 1 begins immediately after the pattern table (e.g. `0x02B8`), the pattern table scanner stops at `min(track_start_offsets)` to prevent reading melodic performance data as phantom drum patterns.
