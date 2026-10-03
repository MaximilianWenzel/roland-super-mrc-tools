# Roland Super-MRC (.SNG) Binary Format Specification

> **Status: Working Reverse-Engineering Reference**  
> This specification documents data structures reverse-engineered from Roland MC-50 `.SNG` floppy disk dumps to support Standard MIDI conversion in `sng2mid`. It reflects empirical findings rather than an official manufacturer specification. Certain hardware flags and proprietary setup parameters remain undocumented. Corrections and sample dumps from vintage Roland hardware owners are welcome.

---

## Disk Organization & Directory Catalog (`MC500DIR.TNB`)

Roland MC-series sequencers format 3.5" double-density (720 KB) floppy disks with a proprietary catalog file named `MC500DIR.TNB`.

The catalog begins at offset `0x0100` and consists of sequential 32-byte directory records:

```text
 0                      16             24    27    31
+----------------------+--------------+-----+-----+
| Song Title (ASCII)   | DOS Stem     | Ext | Pad |
| 16 bytes             | 8 bytes      | 3 B | 4 B |
+----------------------+--------------+-----+-----+
```

- **Song Title (`0x00`–`0x0F`):** Up to 16 ASCII characters, padded with spaces (`0x20`).
- **Filename Stem (`0x10`–`0x17`):** 8-byte uppercase DOS stem (e.g. `TNB0000D`).
- **Extension (`0x18`–`0x1A`):** 3-byte extension (typically `SNG`).
- **Padding (`0x1B`–`0x1F`):** Reserved hardware bytes.

An empty entry or an entry beginning with null bytes (`0x00`) signals the end of the directory.

---

## SNG File Layout Overview

An `.SNG` file stores global song parameters, 24-bit little-endian memory pointers to data streams, performance track descriptors, a rhythm pattern dictionary, and compressed event streams.

```text
+-----------------------------------+ 0x0000
| Header (Title, Pointers, Meter)   |
+-----------------------------------+ 0x0040
| Track Descriptors 1–8             |
+-----------------------------------+ 0x00C0
| Stream Pointers (Slot 12 Rhythm)  |
+-----------------------------------+ 0x00F0
| Initial Tempo & Time Signature    |
+-----------------------------------+ 0x02A0
| Rhythm Pattern Descriptor Table   |
+-----------------------------------+ Offset min(TrackOffsets)
| Performance Track Data (1–8)      |
+-----------------------------------+
| Measure Arrangement Stream (Slot 2)
+-----------------------------------+
| Rhythm Note Records (Slot 12)     |
+-----------------------------------+
| Conductor Track (Slot 3)          |
+-----------------------------------+ Song End Pointer
```

---

## Header Fields & Pointers

All file offsets and stream lengths are encoded as **24-bit unsigned integers in little-endian byte order**:

```python
offset = b0 | (b1 << 8) | (b2 << 16)
```

| Offset Range | Size | Field | Description |
|---|---|---|---|
| `0x0000 - 0x000F` | 16 B | Song Title | Internal ASCII song title, space-padded |
| `0x0010 - 0x0012` | 3 B | Song End Pointer | 24-bit LE byte offset marking song memory limit |
| `0x0020 - 0x0022` | 3 B | Measure Timeline Pointer | 24-bit LE offset to Slot 2 rhythm arrangement |
| `0x0030 - 0x0032` | 3 B | Conductor Stream Pointer | 24-bit LE offset to Slot 3 tempo/meter stream |
| `0x0033 - 0x0035` | 3 B | Conductor Stream Length | 24-bit LE byte length of conductor stream |
| `0x0040 - 0x00BF` | 16 B ea | Track Descriptors (1–8) | Start offset and byte length for Tracks 1–8 |
| `0x00C0 - 0x00C2` | 3 B | Rhythm Stream Pointer | 24-bit LE offset to Slot 12 drum pattern data |
| `0x00F1` | 1 B | Initial Tempo | Song tempo in BPM (5–250) |
| `0x00F8 - 0x00F9` | 2 B | Reserved / Flags | Sequencer flags (`0x00`, `0xFF`). Meter is defined by Pattern 0 beat length (`0x02A5`) or defaults to 4/4 |

---

## Track Descriptors (`0x0040`–`0x00BF`)

The header reserves eight 16-byte descriptor slots for performance tracks 1 through 8:

```text
Track 1: 0x0040 - 0x004F
Track 2: 0x0050 - 0x005F
...
Track 8: 0x00B0 - 0x00BF
```

Within each 16-byte descriptor:
- **Bytes `0x00`–`0x02`:** 24-bit LE start offset.
- **Bytes `0x03`–`0x05`:** 24-bit LE track byte length.
- If both offset and length are zero, the track is empty.

---

## Timebase & Tick Accumulation

- **Resolution:** Fixed at **96 PPQN** (pulses per quarter note). A 4/4 measure spans 384 ticks.
- **Delta Ticks:** Each event tuple contains a 1-byte delta tick value representing elapsed time since the previous event.
- **Timing Skip Opcode (`0xFE`):** Because delta values are 8-bit (`0`–`255`), gaps longer than 255 ticks are encoded with timing skip records:

```text
FE 00 [Count] 00 00 00
```

When encountered, the tick accumulator advances by:

```python
current_tick += count * 256
```

---

## Performance Event Stream Format

Performance track streams consist of sequential 6-byte records terminated by status byte `0xFF`:

```text
 0          1            2          3          4          5
+----------+------------+----------+----------+----------+-----------+
| Status   | Delta Tick | Note/CC  | Vel/Val  | Gate Low | Gate High |
+----------+------------+----------+----------+----------+-----------+
```

### Event Decoding Rules

1. **Advance Delta:**
   ```python
   current_tick += delta_tick
   ```

2. **Note-On (`0x90`–`0x9F`):**
   - Channel: `status & 0x0F`
   - Pitch: `note_byte`
   - Velocity: `vel_byte`
   - Gate Time: `gate_low | (gate_high << 8)`
   - Note-Off is deterministically scheduled at `current_tick + gate_time`.

3. **Control Change (`0xB0`–`0xBF`):**
   - Channel: `status & 0x0F`
   - Controller: `note_byte`
   - Value: `vel_byte`

4. **Program Change (`0xC0`–`0xCF`):**
   - Channel: `status & 0x0F`
   - Program Number: `note_byte`

5. **Pitch Bend (`0xE0`–`0xEF`):**
   - Pitch bend combines `vel_byte` (coarse/MSB) and `note_byte` (fine/LSB) into a 14-bit signed deflection centered at `8192`.

6. **Polyphonic Aftertouch (`0xA0`–`0xAF`) & Channel Aftertouch (`0xD0`–`0xDF`):**
   - Preserved and routed to their respective MIDI channel events.

---

## Rhythm Architecture & Unrolling

Roland Super-MRC uses a two-level pattern sequencer for drum tracks:

### Pattern Descriptor Table (`0x02A0`)
Each pattern is defined by a 22-byte descriptor at `0x02A0 + (pattern_index * 22)`:

```text
 0          1    2    3    4    5    6                  21
+----------+----+----+----+----+----+--------------------+
| Slot12   | ?? | ?? | ?? | ?? | Beat| Pattern Label ASCII|
| Pointer  |    |    |    |    | Len | 16 bytes           |
| (24-bit) |    |    |    |    |     |                    |
+----------+----+----+----+----+----+--------------------+
```

- **Slot 12 Pointer (`0x00`–`0x02`):** 24-bit LE offset relative to the start of the Slot 12 drum data stream.
- **Beat Length (`0x05`):** Number of quarter notes in the pattern (e.g. 4 for a 4/4 measure = 384 ticks).

> **Important Boundary Rule:** The pattern descriptor table must not be parsed blindly until `slot12_ptr`. In sparse files, Track 1 performance data begins immediately after the last pattern (e.g. at `0x02B8`). The table parser must stop at `min(all track start offsets > 0x02A0)` to avoid misinterpreting melodic notes as phantom pattern descriptors.

### Pattern Note Records (Slot 12)
Inside the Slot 12 stream, pattern notes are stored as 3-byte tuples:

```text
 0          1            2
+----------+------------+---------------+
| Note     | Delta Tick | Velocity Code |
+----------+------------+---------------+
```

The stream terminates with byte `0xFF`.

### Measure Arrangement Timeline (Slot 2, `0x0020`)
The song's measure sequence is encoded in Slot 2 as sequential 3-byte entries terminated by `0xFF`:

```text
 0                1          2
+----------------+----------+---------------+
| Pattern Index  | Reserved | Velocity Trim |
| (0-based)      | (1 byte) | (Signed 8-bit)|
+----------------+----------+---------------+
```

- **Pattern Index (`byte 0`):** 0-based physical index into the pattern descriptor table.
  - Special index `0xF4`: Rest measure (generates silence for the duration of the bar).
- **Reserved (`byte 1`):** Hardware flags / reserved byte (typically `0x00` or `0x0F`).
- **Velocity Trim (`byte 2`):** **Signed 8-bit integer** (`-128` to `+127`).
  - Example: `0xFB` represents `-5`.
  - Applied additively to every drum note in the measure:
    ```python
    effective_velocity = max(1, min(127, pattern_velocity + signed_trim))
    ```

### Unrolling Output
The timeline unroller processes each measure entry sequentially, accumulates the measure start tick, applies the measure's velocity trim, and outputs all drum events on MIDI Channel 10 (`channel = 9` in 0-indexed MIDI).

---

## Conductor Stream Format (Slot 3, `0x0030`)

The conductor stream stores dynamic tempo changes and sequencer timing markers as sequential 6-byte records terminated by byte `0xFF`:

```text
 0          1            2          3          4          5
+----------+------------+----------+----------+----------+-----------+
| Opcode   | Delta Tick | Data 1   | Data 2   | Data 3   | Data 4    |
+----------+------------+----------+----------+----------+-----------+
```

### Event Types

1. **Advance Delta:**
   ```python
   current_tick += delta_tick
   ```

2. **Timing Skip (`0xFE`):**
   ```python
   current_tick += count * 256  # byte 2 is count
   ```

3. **Tempo Change (`0xF9`):**
   In Roland Super-MRC, bytes 2 and 3 encode an **8.8 fixed-point scaling factor** (`w1`) relative to the song's initial tempo, where `256 = 1.0x`:
   ```python
   w1 = data[offset + 2] | (data[offset + 3] << 8)
   if w1 > 0:
       tempo_bpm = max(20.0, min(350.0, round(initial_tempo_bpm * (w1 / 256.0))))
   ```
   This proportional scaling allows the sequencer to execute accelerando and ritardando curves relative to the base tempo without storing absolute floating-point rates.

4. **End of Track (`0xFF`):**
   Signals the end of the conductor stream.

