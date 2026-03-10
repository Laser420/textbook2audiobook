# textbook2audiobook — Session Context

## What This Is
A Python CLI tool that captures online textbook pages via screenshot, packages
them for ebook2audiobook, which handles OCR (tesseract) and TTS conversion.
No AI API, no cost.

## Project Location
`/Users/owenlandy/dev/fuckabout/textbook2audiobook/`

## File Structure
```
main.py            # CLI — all 5 commands
session.py         # Session dataclass + JSON persistence
capture.py         # select_region (tkinter overlay) + take_screenshot (screencapture) + CaptureWindow (two-window UI)
preview_server.py  # Legacy: standalone subprocess preview window (no longer used by main flow)
requirements.txt   # mss, Pillow, click, rich
pyproject.toml     # pip install . → exposes `textbook2audiobook` command
PLAN.md            # Implementation plan with completion status
CONTEXT.md         # This file
README.md          # User-facing usage documentation
```

## Current State
- All commands working and tested end-to-end
- `python3 main.py new` — prompts for title, creates session
- `python3 main.py capture` — two-window capture UI, tested and functional
- `python3 main.py pack` — produces PDF in `output/` directory
- `python3 main.py audio` — builds TIFF, passes to ebook2audiobook for OCR + TTS. Tested and produces working audiobook.
- `python3 main.py sessions` — lists all sessions

## Commands
| Command    | What it does |
|------------|-------------|
| `new`      | Create session (prompts for book title). No region pre-selection needed. |
| `capture`  | Opens a resizable transparent frame window. Capture/Redo/Done buttons + keyboard shortcuts. |
| `pack`     | Combine screenshots → PDF in `output/` directory (one image per page, using Pillow) |
| `audio`    | Build multi-page TIFF, pass to ebook2audiobook for OCR + TTS. Output in `output/` directory. |
| `sessions` | Rich table of all saved sessions |

---

## Key Design Decisions

### Capture UI — Two-Window Architecture (CaptureWindow)
The capture UI is a resizable transparent window overlaid on the screen. The user
drags/resizes it to frame their textbook content, then clicks Capture.

**Two windows:**
1. **Frame** — standard macOS window (title bar for move/resize), `alpha=0.20`.
   User sees the textbook through it. A bright green 4px border drawn on a Canvas
   marks the capture boundary.
2. **Bar** — a separate opaque `Toplevel` with `overrideredirect(True)`, positioned
   directly below the frame. Tracks frame position/size via `<Configure>` binding.
   Contains:
   - Button row: Capture, Redo, page count, hints, Done
   - Overlap strip (80px): shows the bottom 1/8 of the last capture so the user
     knows where to start scrolling for the next page

**On capture:** both windows go invisible (frame alpha→0, bar withdrawn) for ~120ms
so `screencapture` gets a clean image of the textbook. Then both reappear.

**No CFRunLoop conflict:** all interaction is via tkinter events/buttons. `input()`
and readline are never called, so the Tcl notifier crash cannot occur. The old
subprocess preview architecture (`preview_server.py`, `PreviewWindow`) is no longer
used — kept for reference only.

**No pre-selected region:** the capture region is determined dynamically from the
window's canvas geometry at capture time. `session.region` is no longer required
(still an optional field in session.json for backward compat).

### TIFF for ebook2audiobook (not PDF)
ebook2audiobook's PDF handler extracts XHTML via PyMuPDF. For image-only PDFs,
`get_text('xhtml')` returns `<img>` data URIs (non-empty), so OCR is never
triggered — resulting in empty text blocks and conversion failure.

ebook2audiobook's **image handler** (`.tiff`, `.png`, etc.) always runs OCR via
tesseract. The `audio` command creates a multi-page TIFF which triggers proper OCR.

The `pack` command still creates a PDF (useful for viewing/archiving), but this
PDF is not used by the `audio` command.

### PDF for viewing (pack command)
Screenshots are combined into a single PDF (one image per page) using
`Pillow Image.save(save_all=True)`. Output goes to `output/` directory.

### Output directory
All generated files go into `output/`:
- `output/<title>.pdf` — from `pack`
- `output/<title>.tiff` — intermediate file from `audio`
- `output/<title>_audiobook/` — ebook2audiobook output from `audio`

### Screenshots
`/usr/sbin/screencapture -x -R x,y,w,h` subprocess — NOT mss. Screencapture
takes logical pixel coords and outputs at full Retina resolution automatically.
No CFRunLoop interaction.

### Session storage
`./sessions/<id>/session.json` + `screenshots/` — stored in the **current
working directory** (not `~/.textbook2audiobook/`), so sessions and screenshots
are visible in the IDE file tree.

`page_count` is derived live from glob count. Screenshots named `0001.png` etc.

### ebook2audiobook
- Path stored in `~/.textbook2audiobook/e2a_path` (global user preference)
- Auto-discovered at `~/ebook2audiobook/` or `./ebook2audiobook/`, else prompts
- Invocation: `bash ebook2audiobook.command --headless --ebook <file>.tiff --output_dir <dir> --language eng`
- Note: the flag is `--output_dir` (NOT `--output_folder`)
- Extra args are forwarded (e.g. `--tts_engine`, `--voice`, `--device`)

### Session picker
When multiple sessions exist and no `-s` flag, `_pick_session()` shows a
numbered table and prompts for selection.

---

## Bugs Found and Fixed

### Bug 1 — Region selector showed black screen (not live screen)
**Problem:** Used `-fullscreen True` which creates a separate macOS desktop space.
**Fix:** Use `overrideredirect(True)` + `geometry()` + `alpha=0.25`.

### Bug 2 — `Tcl_WaitForEvent: Notifier not initialized` crash
**Problem:** readline's CFRunLoop handlers corrupt Tcl notifier when `input()` runs alongside `tkinter.mainloop()`.
**Fix:** Replaced entire input()+tkinter architecture with CaptureWindow (all-tkinter, no readline). Old fix was subprocess isolation (`preview_server.py`), now superseded.

### Bug 3 — `NSWindow should only be instantiated on the main thread!`
**Problem:** Original `PreviewWindow` ran `tk.Tk()` in a daemon thread.
**Fix:** Superseded by CaptureWindow — no threads involved.

### Bug 4–6 — Various UX issues
Fixed: instructions panel, capture mode indication, session picker.

### Bug 7 — `-transparentcolor` not available on macOS
**Problem:** CaptureWindow initially used `wm_attributes("-transparentcolor", ...)` which is Windows-only. macOS tkinter only supports `-alpha, -fullscreen, -modified, -notify, -titlepath, -topmost, -transparent, -type`.
**Fix:** Two-window approach — semi-transparent frame (alpha=0.20) + separate opaque Toplevel bar.

### Bug 8 — ebook2audiobook rejects `.cbz` format
**Problem:** ebook2audiobook's README lists CBZ as supported, but their actual `ebook_formats` list in `lib/conf.py` does NOT include `.cbz`. Error: `Unsupported file format: .cbz`.
**Fix:** Changed `pack` to produce a PDF instead of CBZ.

### Bug 9 — `--output_folder` unrecognized by ebook2audiobook
**Problem:** The correct flag is `--output_dir`, not `--output_folder`.
**Fix:** Updated the `audio` command.

### Bug 10 — ebook2audiobook skips OCR on image-based PDFs
**Problem:** PyMuPDF's `get_text('xhtml')` returns `<img>` data URIs for image-embedded PDF pages (non-empty), so ebook2audiobook's OCR fallback never triggers. Result: empty text blocks, `get_blocks() failed!`.
**Fix:** `audio` command now creates a multi-page TIFF instead of reusing the PDF. ebook2audiobook's image handler always OCRs `.tiff` files via tesseract.

---

## Coordinate System
Region coords are in **logical pixels** (tkinter coordinate space):
- `CaptureWindow.get_region()` uses `canvas.winfo_rootx()/rooty()` — logical pixels
- `screencapture -R` takes logical pixel coords natively
- mss is ONLY used in `check_screen_permission()` (main thread, before any UI)

---

## Environment
- macOS Darwin 25.3.0 (Sequoia)
- Python 3.13 (Homebrew/Miniforge, at `python3` in PATH)
- Dependencies: mss, Pillow, click, rich (installed via `pip3 install -r requirements.txt`)
- External tools: tesseract (`/opt/homebrew/bin/tesseract`), calibre/ebook-convert (`/opt/homebrew/bin/ebook-convert`)
- ebook2audiobook: `/Users/owenlandy/dev/fuckabout/ebook2audiobook/`
- Run as: `python3 main.py <command>`
