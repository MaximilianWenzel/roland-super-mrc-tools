"""Tests for the sng2mid CLI tool."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from roland_super_mrc.cli import app
from tests.conftest import create_minimal_sng_binary

runner = CliRunner()


def test_cli_convert_success(sample_sng_path: Path, tmp_path: Path) -> None:
    """Verify sng2mid convert generates a valid .mid file on disk."""
    out_mid = tmp_path / "custom_output.mid"
    result = runner.invoke(app, ["convert", str(sample_sng_path), "-o", str(out_mid)])

    assert result.exit_code == 0
    assert "Successfully converted" in result.stdout
    assert out_mid.exists()
    assert out_mid.stat().st_size > 0


def test_cli_convert_verbose(sample_sng_path: Path, tmp_path: Path) -> None:
    """Verify sng2mid convert --verbose prints song metadata and track breakdown."""
    out_mid = tmp_path / "verbose_output.mid"
    result = runner.invoke(app, ["convert", str(sample_sng_path), "-o", str(out_mid), "--verbose"])

    assert result.exit_code == 0
    assert "Title: AUTUMN GROOVE" in result.stdout
    assert "124 BPM" in result.stdout
    assert "Performance Tracks: 1" in result.stdout
    assert "Rhythm (Ch 10)" in result.stdout


def test_cli_convert_corrupt_file(tmp_path: Path) -> None:
    """Verify sng2mid convert fails gracefully with exit code 1 on malformed binary."""
    bad_file = tmp_path / "corrupt.sng"
    bad_file.write_bytes(b"NOT_A_VALID_SNG_HEADER")

    result = runner.invoke(app, ["convert", str(bad_file)])

    assert result.exit_code == 1
    assert "Error parsing Super-MRC file" in result.output


def test_cli_inspect_success(sample_sng_path: Path) -> None:
    """Verify sng2mid inspect displays binary metadata table."""
    result = runner.invoke(app, ["inspect", str(sample_sng_path)])

    assert result.exit_code == 0
    assert "AUTUMN GROOVE" in result.stdout
    assert "124 BPM" in result.stdout
    assert "4/4" in result.stdout
    assert "96" in result.stdout
    assert "Active Performance Tracks" in result.stdout


def test_cli_inspect_corrupt_file(tmp_path: Path) -> None:
    """Verify sng2mid inspect fails gracefully with exit code 1 on malformed input."""
    bad_file = tmp_path / "broken.sng"
    bad_file.write_bytes(b"\x00" * 30)

    result = runner.invoke(app, ["inspect", str(bad_file)])

    assert result.exit_code == 1
    assert "Error inspecting file" in result.output


def test_cli_batch_success(tmp_path: Path) -> None:
    """Verify sng2mid batch recursively converts a directory tree of .SNG files."""
    in_dir = tmp_path / "floppy_root"
    in_dir.mkdir()
    sub_dir = in_dir / "folder_a"
    sub_dir.mkdir()

    sng_data_1 = create_minimal_sng_binary(title="SONG ONE", bpm=100)
    sng_data_2 = create_minimal_sng_binary(title="SONG TWO", bpm=140)

    (in_dir / "SONG1.SNG").write_bytes(sng_data_1)
    (sub_dir / "SONG2.sng").write_bytes(sng_data_2)

    out_dir = tmp_path / "converted_out"

    result = runner.invoke(app, ["batch", str(in_dir), "-o", str(out_dir), "--recursive"])

    assert result.exit_code == 0
    assert "Found 2 Super-MRC files" in result.stdout
    assert "2 converted successfully, 0 failed" in result.stdout
    assert (out_dir / "01 - SONG ONE.mid").exists()
    assert (out_dir / "folder_a" / "01 - SONG TWO.mid").exists()

    # Also test --naming original
    out_dir_orig = tmp_path / "converted_orig"
    res_orig = runner.invoke(
        app,
        ["batch", str(in_dir), "-o", str(out_dir_orig), "--recursive", "--naming", "original"],
    )
    assert res_orig.exit_code == 0
    assert (out_dir_orig / "SONG1.mid").exists()
    assert (out_dir_orig / "folder_a" / "SONG2.mid").exists()


def test_cli_batch_empty_directory(tmp_path: Path) -> None:
    """Verify sng2mid batch handles empty directory without failing."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    result = runner.invoke(app, ["batch", str(empty_dir)])

    assert result.exit_code == 0
    assert "No .SNG files found" in result.stdout
