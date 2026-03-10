# textbook2audiobook — Implementation Plan

## Completion Status

| Section | Topic | Status |
|---------|-------|--------|
| 1 | Project Structure & Dependencies | Complete |
| 2 | Session Management | Complete |
| 3 | Screen Region Selector | Complete (redesigned — see notes) |
| 4 | Capture Loop | Complete (redesigned — see notes) |
| 5 | Packing Output | Complete (PDF + TIFF, not CBZ) |
| 6 | ebook2audiobook Integration | Complete (TIFF input, not CBZ/PDF) |
| 7 | Install & Distribution | Complete (running via `python3 main.py`, not installed CLI) |

**Key deviations from original plan:**
- **Section 3**: Region selector removed. The primary capture UI uses a resizable transparent window — no pre-selected region needed.
- **Section 4**: Capture loop replaced with CaptureWindow (all-tkinter two-window UI). No `input()` loop, no preview thread, no queue-based communication.
- **Section 5**: CBZ replaced with PDF (for viewing) and TIFF (for audio conversion). ebook2audiobook does not actually support CBZ despite their README.
- **Section 6**: Audio command passes a multi-page TIFF (not PDF/CBZ) because ebook2audiobook skips OCR on image-embedded PDFs.
- **Section 7**: CLI is run as `python3 main.py <command>`. The `pyproject.toml` install entry point exists but is not the primary usage path.

---

## Overview
A lightweight Python CLI that captures online textbook pages via screenshot,
packages them as a multi-page TIFF, and passes that to ebook2audiobook
for OCR and TTS conversion. No AI API. No cost beyond ebook2audiobook itself.

---

## Section 1 — Project Structure & Dependencies

### 1.1 File Layout

```
textbook2audiobook/
├── main.py            # CLI entry point — click group + all commands
├── session.py         # Session dataclass and JSON persistence
├── capture.py         # CaptureWindow UI + take_screenshot
├── requirements.txt   # Dependencies
├── pyproject.toml     # Install config
├── PLAN.md            # This file
├── CONTEXT.md         # Session context for development
└── README.md          # Usage documentation
```

### 1.2 Dependencies

```
mss>=9.0.0       # Screen permission check only (not used for capture)
Pillow>=10.4.0   # Image handling, PDF/TIFF creation, overlap thumbnails
click>=8.1.0     # CLI commands and options
rich>=13.7.0     # Terminal UI — panels, tables
```

`tkinter` ships with Python's standard library — no install needed.

### 1.3 Commands

| Command    | Purpose |
|------------|---------|
| `new`      | Create a new session (prompts for book title) |
| `capture`  | Open the two-window capture UI for the active session |
| `pack`     | Package screenshots into a PDF in `output/` |
| `audio`    | Build TIFF, pass to ebook2audiobook for OCR + TTS |
| `sessions` | List all saved sessions |

---

## Section 2 — Session Management

### 2.1 Storage Layout

```
./sessions/
└── <session_id>/
    ├── session.json       # metadata
    └── screenshots/
        ├── 0001.png
        ├── 0002.png
        └── ...
```

Sessions are stored in the **current working directory** (`./sessions/`), not
in `~/.textbook2audiobook/`, so they are visible in the IDE file tree.

`session_id` is a short 8-character hex string. Screenshots are named with
zero-padded numbers so they sort correctly.

### 2.2 Data Model

**`Session` dataclass**

| Field        | Type   | Description |
|--------------|--------|-------------|
| `session_id` | str    | 8-char hex ID |
| `title`      | str    | Book title (used for output filename) |
| `created_at` | str    | ISO timestamp |

`page_count` is derived from the number of `.png` files in `screenshots/`,
not stored in session.json.

### 2.3 Key Functions

| Function | Behaviour |
|----------|-----------|
| `Session.create(title)` | New session with ID and timestamp |
| `Session.save()` | Write session.json, create dirs |
| `Session.load(session_id)` | Read session.json |
| `Session.list_all()` | All sessions sorted by created_at |
| `session.screenshots_dir()` | Path to screenshots folder |
| `session.next_filename()` | Zero-padded next filename e.g. `0023.png` |
| `session.title_slug()` | URL-safe title for filenames |

---

## Section 3 — Capture UI

### 3.1 Overview

The capture UI is a **two-window tkinter application** (`CaptureWindow` class
in `capture.py`). It replaces the original plan's region-selector + input-loop
architecture.

### 3.2 Two-Window Architecture

1. **Frame** — a standard macOS window (resizable via title bar) with low
   alpha (~0.20). The user sees the textbook through it. A bright green 4px
   border drawn on a Canvas marks the capture boundary.

2. **Bar** — a separate opaque Toplevel positioned directly below the frame.
   Contains:
   - Button row: Capture, Redo, page count, keyboard hints, Done
   - Overlap strip (80px): shows the bottom 1/8 of the last capture

### 3.3 Capture Flow

```
1. User runs `python3 main.py capture`
2. CaptureWindow opens — frame + bar appear on screen
3. User drags/resizes the frame over their textbook content
4. Click "Capture" (or press Enter):
   a. Frame goes fully transparent (alpha → 0), bar hides
   b. Wait 120ms for macOS compositor
   c. screencapture -R captures the region inside the green border
   d. Frame and bar reappear
   e. Overlap strip updates with bottom 1/8 of captured image
5. User scrolls textbook to next page, aligning with overlap strip
6. Repeat step 4
7. Click "Done" (or press q/Escape) to exit
```

### 3.4 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Capture |
| r / R | Redo (delete last screenshot) |
| q / Q / Escape | Done |

### 3.5 Why Not input() + Preview Thread

The original plan used `input()` for the capture loop and a daemon thread for
the preview window. This caused `Tcl_WaitForEvent: Notifier not initialized`
crashes because readline's CFRunLoop handlers conflict with tkinter's Tcl
notifier on macOS. The all-tkinter CaptureWindow avoids this entirely.

---

## Section 4 — Packing Output

### 4.1 PDF (pack command)

The `pack` command creates a PDF for viewing/archiving:

```python
images = [Image.open(p).convert("RGB") for p in screenshots]
images[0].save(out, save_all=True, append_images=images[1:])
```

Output: `output/<title_slug>/<title_slug>.pdf`

### 4.2 TIFF (audio command)

The `audio` command creates a multi-page TIFF for ebook2audiobook:

```python
images[0].save(out, save_all=True, append_images=images[1:], compression="tiff_deflate")
```

Output: `output/<title_slug>/<title_slug>.tiff`

### 4.3 Why TIFF for Audio, Not PDF

ebook2audiobook's PDF handler extracts XHTML via PyMuPDF. For image-only PDFs,
`get_text('xhtml')` returns `<img>` data URIs (non-empty text), so OCR is never
triggered. The image handler (`.tiff`) always OCRs via tesseract.

### 4.4 Why Not CBZ

ebook2audiobook's README lists CBZ as supported, but their `ebook_formats` list
in `lib/conf.py` does not include `.cbz`. It fails with `Unsupported file format`.

---

## Section 5 — ebook2audiobook Integration

### 5.1 Locating ebook2audiobook

Path stored in `~/.textbook2audiobook/e2a_path` (plain text file).
Discovery order:

```
1. Check ~/.textbook2audiobook/e2a_path for a stored path
2. Check ~/ebook2audiobook/
3. Check ./ebook2audiobook/
4. Prompt user, validate ebook2audiobook.command exists, save path
```

### 5.2 Subprocess Call

```python
cmd = [
    "bash",
    str((e2a_path / "ebook2audiobook.command").resolve()),
    "--headless",
    "--ebook", str(tiff_path.resolve()),
    "--output_dir", str(output_dir.resolve()),
    "--language", "eng",
    "--speed", str(speed),
] + list(extra_args)
```

`--speed` (1.0–3.0) controls narration speed (XTTSv2 only). Prompted
interactively if not provided via `--speed` flag.

Extra args from the user are forwarded directly to ebook2audiobook (e.g.
`--voice`, `--tts_engine`, `--device`).

### 5.3 Output Directory

Audiobook written to `output/<title_slug>/` by default (same directory as PDF and TIFF).
Overridable with `--output` on the `audio` command.

### 5.4 Error Handling

| Failure | Response |
|---------|----------|
| `ebook2audiobook.command` not found at stored path | Clear stored path, re-prompt |
| subprocess exits non-zero | Print error, direct user to output above |
| No screenshots to pack | Abort — nothing to convert |

---

## Section 6 — Install & Distribution

### 6.1 Running

```bash
cd textbook2audiobook
pip3 install -r requirements.txt
python3 main.py new
python3 main.py capture
python3 main.py pack
python3 main.py audio
```

### 6.2 `pyproject.toml`

A `pyproject.toml` exists for optional `pip install .` which exposes the
`textbook2audiobook` CLI command, but the primary usage path is
`python3 main.py <command>`.

### 6.3 macOS Screen Recording Permission

mss returns a silent black image when Screen Recording permission is not
granted. Checked at the start of `capture` by sampling a small region:

```python
def check_screen_permission() -> bool:
    with mss.mss() as sct:
        shot = sct.grab({"left": 0, "top": 0, "width": 50, "height": 50})
        return any(b != 0 for b in shot.rgb[:150])
```

---
