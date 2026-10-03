"""Command-line interface for Roland Super-MRC Tools (sng2mid)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from roland_super_mrc.catalog import parse_mc500_directory, resolve_output_filename
from roland_super_mrc.exceptions import SuperMrcError
from roland_super_mrc.models import NamingMode
from roland_super_mrc.parser import parse_sng_file
from roland_super_mrc.writer import write_midi_file

app = typer.Typer(
    name="sng2mid",
    help="Bit-accurate Roland Super-MRC (.SNG) to Standard MIDI (SMF) converter and inspection tools.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.command()
def convert(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the Roland Super-MRC (.SNG) file to convert.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output: Annotated[
        Optional[Path],
        typer.Option(
            "--output",
            "-o",
            help="Destination path for the converted .mid file (default: same name in same directory).",
        ),
    ] = None,
    format_type: Annotated[
        int,
        typer.Option(
            "--format",
            "-f",
            help="Standard MIDI File format: 1 (multi-track) or 0 (single-track).",
        ),
    ] = 1,
    naming: Annotated[
        NamingMode,
        typer.Option(
            "--naming",
            "-n",
            help="Filename strategy if --output is omitted: 'original', 'title', or 'index-title'.",
        ),
    ] = NamingMode.ORIGINAL,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Display detailed track breakdown and event counts.",
        ),
    ] = False,
) -> None:
    """Convert a single Roland Super-MRC (.SNG) file to Standard MIDI (SMF)."""
    try:
        song = parse_sng_file(input_path)

        if output is None:
            catalog = parse_mc500_directory(input_path.parent)
            out_name = resolve_output_filename(input_path, song.title, mode=naming, catalog=catalog)
            output = input_path.with_name(out_name)
        elif output.is_dir():
            catalog = parse_mc500_directory(input_path.parent)
            out_name = resolve_output_filename(input_path, song.title, mode=naming, catalog=catalog)
            output = output / out_name

        out_file = write_midi_file(song, output, format_type=format_type)

        console.print(
            f"[green][OK][/green] Successfully converted [bold]{input_path.name}[/bold] -> [cyan]{out_file.name}[/cyan]"
        )

        if verbose:
            console.print(f"  Title: [bold]{song.title}[/bold]")
            console.print(
                f"  Tempo: {song.initial_tempo_bpm} BPM | Time Signature: {song.time_signature[0]}/{song.time_signature[1]} | PPQN: {song.ppqn}"
            )
            console.print(f"  Performance Tracks: {len(song.performance_tracks)}")
            for trk in song.performance_tracks:
                notes = sum(1 for e in trk.events if (e.status & 0xF0) == 0x90 and e.data2 > 0)
                console.print(f"    - {trk.name}: {len(trk.events)} events ({notes} notes)")
            if song.rhythm_events:
                drum_notes = sum(
                    1 for e in song.rhythm_events if (e.status & 0xF0) == 0x90 and e.data2 > 0
                )
                console.print(
                    f"    - Rhythm (Ch 10): {len(song.rhythm_events)} events ({drum_notes} drum hits in {song.measure_count} measures)"
                )

    except SuperMrcError as err:
        err_console.print(f"[red]Error parsing Super-MRC file:[/red] {err}")
        raise typer.Exit(code=1) from err
    except Exception as err:
        err_console.print(f"[red]Unexpected error:[/red] {err}")
        raise typer.Exit(code=2) from err


@app.command()
def inspect(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the Roland Super-MRC (.SNG) file to inspect.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
) -> None:
    """Inspect and display internal binary metadata of a Roland Super-MRC file."""
    try:
        song = parse_sng_file(input_path)

        table = Table(title=f"Roland Super-MRC Inspection: {input_path.name}")
        table.add_column("Property", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")

        table.add_row("Song Title", song.title)
        table.add_row("Initial Tempo", f"{song.initial_tempo_bpm} BPM")
        table.add_row("Time Signature", f"{song.time_signature[0]}/{song.time_signature[1]}")
        table.add_row("PPQN Timebase", str(song.ppqn))
        table.add_row("Active Performance Tracks", str(len(song.performance_tracks)))
        table.add_row("Dynamic Tempo Changes", str(len(song.tempo_changes)))
        table.add_row("Rhythm Arrangement Measures", str(song.measure_count))
        table.add_row("Rhythm Channel 10 Events", str(len(song.rhythm_events)))

        console.print(table)

        if song.performance_tracks:
            trk_table = Table(title="Performance Tracks Breakdown")
            trk_table.add_column("Track", style="magenta")
            trk_table.add_column("Events", justify="right")
            trk_table.add_column("Note Count", justify="right")
            trk_table.add_column("Channels Used", style="yellow")

            for trk in song.performance_tracks:
                notes = sum(1 for e in trk.events if (e.status & 0xF0) == 0x90 and e.data2 > 0)
                channels = sorted(list({e.channel + 1 for e in trk.events}))
                trk_table.add_row(
                    trk.name,
                    str(len(trk.events)),
                    str(notes),
                    ", ".join(map(str, channels)) if channels else "None",
                )

            console.print(trk_table)

    except SuperMrcError as err:
        err_console.print(f"[red]Error inspecting file:[/red] {err}")
        raise typer.Exit(code=1) from err


@app.command()
def batch(
    input_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory containing .SNG floppy disk files.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            readable=True,
        ),
    ],
    output_dir: Annotated[
        Optional[Path],
        typer.Option(
            "--output-dir",
            "-o",
            help="Destination folder for exported MIDI files (default: same as input_dir).",
        ),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option(
            "--recursive",
            "-r",
            help="Recursively scan subfolders for .SNG files.",
        ),
    ] = False,
    format_type: Annotated[
        int,
        typer.Option(
            "--format",
            "-f",
            help="MIDI file format: 1 (default) or 0.",
        ),
    ] = 1,
    naming: Annotated[
        NamingMode,
        typer.Option(
            "--naming",
            "-n",
            help="Output naming: 'index-title' (e.g. 01 - Song.mid), 'title', or 'original'.",
        ),
    ] = NamingMode.INDEX_TITLE,
) -> None:
    """Batch convert all Roland Super-MRC (.SNG) files in a directory."""
    if output_dir is None:
        output_dir = input_dir

    pattern = "**/*.[sS][nN][gG]" if recursive else "*.[sS][nN][gG]"
    files = sorted(list(input_dir.glob(pattern)))

    if not files:
        console.print(f"[yellow]No .SNG files found in {input_dir}[/yellow]")
        return

    console.print(f"Found [bold]{len(files)}[/bold] Super-MRC files to convert...")

    # Group files by parent directory to maintain index sequence per disk
    dir_to_files: dict[Path, list[Path]] = {}
    for sng_file in files:
        dir_to_files.setdefault(sng_file.parent, []).append(sng_file)

    success = 0
    failures = 0

    for parent_dir, dir_files in dir_to_files.items():
        catalog = parse_mc500_directory(parent_dir)
        rel_dir = parent_dir.relative_to(input_dir)
        target_dir = output_dir / rel_dir

        for idx, sng_file in enumerate(dir_files, start=1):
            try:
                song = parse_sng_file(sng_file)
                out_name = resolve_output_filename(
                    sng_file,
                    song.title,
                    index=idx,
                    mode=naming,
                    catalog=catalog,
                )
                target_mid = target_dir / out_name
                write_midi_file(song, target_mid, format_type=format_type)
                success += 1
            except Exception as err:
                err_console.print(f"[red]Failed {sng_file.name}:[/red] {err}")
                failures += 1

    console.print(
        f"\n[bold green]Batch complete:[/bold green] {success} converted successfully, {failures} failed."
    )


if __name__ == "__main__":
    app()
