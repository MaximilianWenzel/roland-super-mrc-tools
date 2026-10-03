"""Tests for MC-500 directory catalog parsing and filename resolution."""

from __future__ import annotations

from pathlib import Path

from roland_super_mrc.catalog import (
    parse_mc500_directory,
    resolve_output_filename,
    sanitize_filename,
)
from roland_super_mrc.models import NamingMode


def test_sanitize_filename() -> None:
    """Verify filesystem illegal characters are cleaned."""
    assert sanitize_filename('Song: "A/B" <Test>?') == "Song_ _A_B_ _Test__"
    assert sanitize_filename("   Clean Title   ") == "Clean Title"


def test_resolve_output_filename_modes() -> None:
    """Verify original, title, and index-title naming modes."""
    sng_path = Path("TNB00000.SNG")
    title = "AUTUMN LEAVES"

    # ORIGINAL mode
    assert resolve_output_filename(sng_path, title, mode=NamingMode.ORIGINAL) == "TNB00000.mid"

    # TITLE mode
    assert resolve_output_filename(sng_path, title, mode=NamingMode.TITLE) == "AUTUMN LEAVES.mid"

    # INDEX_TITLE mode
    assert (
        resolve_output_filename(sng_path, title, index=1, mode=NamingMode.INDEX_TITLE)
        == "01 - AUTUMN LEAVES.mid"
    )
    assert (
        resolve_output_filename(sng_path, title, index=14, mode=NamingMode.INDEX_TITLE)
        == "14 - AUTUMN LEAVES.mid"
    )


def test_parse_mc500_directory_synthetic(tmp_path: Path) -> None:
    """Verify parse_mc500_directory extracts titles from 32-byte records."""
    dir_buf = bytearray(0x0200)
    # Entry at 0x0100: flag 0x80, fn='TNB00000', ext='SNG', title='MY SONG'
    dir_buf[0x0100] = 0x80
    dir_buf[0x0105:0x010D] = b"TNB00000"
    dir_buf[0x010D:0x0110] = b"SNG"
    dir_buf[0x0110:0x0120] = b"MY SONG         "

    mc500_file = tmp_path / "MC500DIR.TNB"
    mc500_file.write_bytes(dir_buf)

    name_map = parse_mc500_directory(tmp_path)
    assert name_map.get("TNB00000.SNG") == "MY SONG"
    assert name_map.get("TNB00000") == "MY SONG"

    # Test resolve with catalog
    out_name = resolve_output_filename(
        tmp_path / "TNB00000.SNG",
        "Raw Title",
        index=1,
        mode=NamingMode.INDEX_TITLE,
        catalog=name_map,
    )
    assert out_name == "01 - MY SONG.mid"
