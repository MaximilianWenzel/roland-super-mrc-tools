"""Catalog parser and filename resolution for Roland MC-50 / MC-500 floppy disks."""

from __future__ import annotations

import re
from pathlib import Path

from roland_super_mrc.models import NamingMode

# Reserved filesystem characters across Windows, macOS, Linux
_INVALID_CHARS_PATTERN = re.compile(r'[\\/*?:"<>|]')


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be a safe filename across operating systems."""
    cleaned = _INVALID_CHARS_PATTERN.sub("_", name)
    # Collapse consecutive whitespace and strip
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_mc500_directory(disk_folder: Path) -> dict[str, str]:
    """Parse Roland hardware MC500DIR.TNB catalog if present in disk folder.

    Returns a mapping of filename (e.g. 'TNB00000.SNG') to song title.
    """
    catalog_map: dict[str, str] = {}
    dir_file = disk_folder / "MC500DIR.TNB"

    if not dir_file.is_file():
        return catalog_map

    data = dir_file.read_bytes()
    for i in range(0x0100, len(data), 32):
        entry = data[i : i + 32]
        if len(entry) < 32 or entry[0] != 0x80:
            continue

        fn_base = entry[5:13].decode("latin1", errors="ignore").strip()
        fn_ext = entry[13:16].decode("latin1", errors="ignore").strip()
        full_fn = f"{fn_base}.{fn_ext}".upper() if fn_ext else fn_base.upper()
        title = entry[16:32].decode("latin1", errors="ignore").strip()

        if full_fn and title:
            catalog_map[full_fn] = title
            catalog_map[fn_base.upper()] = title

    return catalog_map


def resolve_output_filename(
    sng_path: Path,
    song_title: str,
    index: int | None = None,
    mode: NamingMode = NamingMode.INDEX_TITLE,
    catalog: dict[str, str] | None = None,
) -> str:
    """Compute the sanitized target MIDI filename based on the specified NamingMode."""
    if mode == NamingMode.ORIGINAL:
        return sng_path.with_suffix(".mid").name

    effective_title = ""
    if catalog:
        effective_title = catalog.get(sng_path.name.upper(), "") or catalog.get(
            sng_path.stem.upper(), ""
        )

    if not effective_title:
        effective_title = song_title if song_title and song_title != "Untitled" else sng_path.stem

    clean_title = sanitize_filename(effective_title)
    if not clean_title:
        clean_title = sanitize_filename(sng_path.stem)

    if mode == NamingMode.INDEX_TITLE and index is not None:
        return f"{index:02d} - {clean_title}.mid"

    return f"{clean_title}.mid"
