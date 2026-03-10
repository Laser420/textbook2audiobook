from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from capture import CaptureWindow, check_screen_permission
from session import Session

console = Console()

E2A_PATH_FILE = Path.home() / ".textbook2audiobook" / "e2a_path"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pick_session(session_id: str | None) -> Session:
    all_sessions = Session.list_all()
    if not all_sessions:
        console.print("[red]No sessions found. Run 'new' first.[/red]")
        sys.exit(1)
    if session_id:
        try:
            return Session.load(session_id)
        except FileNotFoundError:
            console.print(f"[red]Session '{session_id}' not found.[/red]")
            sys.exit(1)
    if len(all_sessions) == 1:
        return all_sessions[0]

    # Multiple sessions — show a numbered picker
    recent = list(reversed(all_sessions))
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Title")
    table.add_column("Pages", justify="right", style="dim")
    table.add_column("Created", style="dim")
    for i, s in enumerate(recent, 1):
        table.add_row(str(i), s.title, str(s.page_count), s.created_at[:10])
    console.print(table)

    while True:
        raw = click.prompt("Session number", default="1")
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(recent):
                return recent[idx]
        except ValueError:
            pass
        console.print("[red]Enter a number from the list.[/red]")


def _get_e2a_path() -> Path:
    """Locate the ebook2audiobook directory, prompting the user if needed."""
    if E2A_PATH_FILE.exists():
        p = Path(E2A_PATH_FILE.read_text().strip())
        if (p / "ebook2audiobook.command").exists():
            return p
        console.print("[yellow]Stored ebook2audiobook path is no longer valid.[/yellow]")

    for candidate in [Path.home() / "ebook2audiobook", Path("ebook2audiobook")]:
        if (candidate / "ebook2audiobook.command").exists():
            E2A_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
            E2A_PATH_FILE.write_text(str(candidate))
            return candidate

    while True:
        raw = click.prompt("Enter the path to your ebook2audiobook directory").strip()
        p = Path(raw).expanduser()
        if (p / "ebook2audiobook.command").exists():
            E2A_PATH_FILE.parent.mkdir(parents=True, exist_ok=True)
            E2A_PATH_FILE.write_text(str(p))
            return p
        console.print("[red]ebook2audiobook.command not found there — try again.[/red]")


def _pack_session(session: Session, out: Path, fmt: str = "pdf") -> Path:
    """Combine session screenshots into a single file.

    fmt="pdf"  → image-based PDF (for viewing/archiving)
    fmt="tiff" → multi-page TIFF (for ebook2audiobook OCR)
    """
    from PIL import Image

    screenshots = sorted(session.screenshots_dir().glob("*.png"))
    if not screenshots:
        console.print("[red]No screenshots to pack.[/red]")
        sys.exit(1)

    out.parent.mkdir(parents=True, exist_ok=True)
    images = [Image.open(p).convert("RGB") for p in screenshots]

    if fmt == "tiff":
        images[0].save(
            out, save_all=True, append_images=images[1:],
            compression="tiff_deflate",
        )
    else:
        images[0].save(out, save_all=True, append_images=images[1:])
    return out


def _require_screen_permission() -> None:
    if not check_screen_permission():
        console.print(Panel(
            "Screen Recording permission is required.\n\n"
            "  1. Open System Settings → Privacy & Security → Screen Recording\n"
            "  2. Enable Terminal\n"
            "  3. Re-run this command",
            title="[red]Permission Required[/red]",
            border_style="red",
        ))
        sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """textbook2audiobook — Capture your textbook and convert it to an audiobook."""


@cli.command()
def new() -> None:
    """Create a new capture session."""
    title = click.prompt("Book title")
    session = Session.create(title=title)
    session.save()

    console.print(
        f"\n[green]✓ Session created:[/green] [bold]{session.session_id}[/bold] — {session.title}\n\n"
        f"Run [bold]python3 main.py capture[/bold] to start capturing pages.\n"
        f"A resizable frame window will open — drag it over your textbook content."
    )


@cli.command()
@click.option("--session", "-s", "session_id", default=None, help="Session ID (default: most recent)")
def capture(session_id: str | None) -> None:
    """Capture pages using a resizable transparent frame window.

    A window opens over your screen — drag and resize it to frame your
    textbook content, then click Capture (or press Enter) for each page.
    """
    _require_screen_permission()

    session = _pick_session(session_id)

    console.print(
        f"[cyan]Opening capture window for:[/cyan] [bold]{session.title}[/bold]  "
        f"[dim]({session.page_count} pages so far)[/dim]\n"
        "[dim]Resize the frame over your textbook, then click Capture or press Enter.[/dim]"
    )

    CaptureWindow().run(session)

    console.print(Panel.fit(
        f"[green]Session saved.[/green]\n"
        f"{session.page_count} screenshots captured.\n\n"
        f"Run [bold]python3 main.py pack[/bold] to build the PDF.",
        border_style="green",
    ))


@cli.command()
@click.option("--session", "-s", "session_id", default=None, help="Session ID (default: most recent)")
@click.option("--output", "-o", default=None, help="Output .pdf path")
def pack(session_id: str | None, output: str | None) -> None:
    """Package captured screenshots into a PDF (one image per page)."""
    session = _pick_session(session_id)
    if output:
        out = Path(output)
    else:
        out = Path("output") / session.title_slug() / f"{session.title_slug()}.pdf"

    count = session.page_count
    if count == 0:
        console.print("[red]No screenshots found. Run 'capture' first.[/red]")
        sys.exit(1)

    console.print(f"[cyan]Packing {count} pages…[/cyan]")
    _pack_session(session, out)

    size_mb = out.stat().st_size / 1_048_576
    console.print(
        f"[green]✓ PDF created:[/green] {out} ({size_mb:.1f} MB, {count} pages)\n\n"
        f"Run [bold]python3 main.py audio[/bold] to convert."
    )


@cli.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
@click.option("--session", "-s", "session_id", default=None, help="Session ID (default: most recent)")
@click.option("--pdf", default=None, help="Input file path (default: auto-builds TIFF from screenshots)")
@click.option("--output", "-o", default=None, help="Output folder for audiobook files")
@click.option("--speed", type=click.FloatRange(1.0, 3.0), default=None, help="Narration speed (1.0–3.0, default: prompt)")
@click.argument("extra_args", nargs=-1, type=click.UNPROCESSED)
def audio(
    session_id: str | None,
    pdf: str | None,
    output: str | None,
    speed: float | None,
    extra_args: tuple,
) -> None:
    """Convert captured pages to an audiobook via ebook2audiobook.

    Creates a multi-page TIFF from screenshots (ebook2audiobook OCRs image
    files properly, unlike image-embedded PDFs where OCR is bypassed).

    Any unrecognised flags are forwarded directly to ebook2audiobook
    (e.g. --voice, --tts_engine, --device).
    """
    session = _pick_session(session_id)

    # Build a multi-page TIFF for ebook2audiobook (triggers OCR)
    output_base = Path("output") / session.title_slug()
    tiff_path = output_base / f"{session.title_slug()}.tiff"
    if pdf:
        # User explicitly provided a file — use it as-is
        tiff_path = Path(pdf)
    else:
        console.print("[cyan]Building TIFF for OCR…[/cyan]")
        _pack_session(session, tiff_path, fmt="tiff")
        console.print(f"[green]✓ TIFF created: {tiff_path}[/green]")

    if speed is None:
        speed = click.prompt(
            "Narration speed (1.0 = normal, 1.3 = slightly faster, up to 3.0)",
            type=click.FloatRange(1.0, 3.0),
            default=1.0,
        )

    e2a_path = _get_e2a_path()
    output_dir = Path(output) if output else output_base
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "bash",
        str((e2a_path / "ebook2audiobook.command").resolve()),
        "--headless",
        "--ebook", str(tiff_path.resolve()),
        "--output_dir", str(output_dir.resolve()),
        "--language", "eng",
        "--speed", str(speed),
    ] + list(extra_args)

    console.print(f"[cyan]Launching ebook2audiobook…[/cyan]")
    console.print(f"[dim]{' '.join(cmd)}[/dim]\n")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        console.print("[red]ebook2audiobook exited with an error — check output above.[/red]")
        sys.exit(1)
    except FileNotFoundError:
        console.print("[red]Could not execute ebook2audiobook.command — check the path.[/red]")
        E2A_PATH_FILE.unlink(missing_ok=True)
        sys.exit(1)


@cli.command(name="sessions")
def list_sessions() -> None:
    """List all saved capture sessions."""
    sessions = Session.list_all()
    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Capture Sessions")
    table.add_column("ID", style="bold cyan")
    table.add_column("Title")
    table.add_column("Pages", justify="right")
    table.add_column("Created")

    for s in reversed(sessions):
        table.add_row(s.session_id, s.title, str(s.page_count), s.created_at[:16])

    console.print(table)


if __name__ == "__main__":
    cli()
