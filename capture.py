from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path

import mss
from PIL import Image, ImageTk

from session import Session


# ── Permission check ─────────────────────────────────────────────────────────

def check_screen_permission() -> bool:
    """Return False if macOS is returning black frames (permission denied)."""
    with mss.mss() as sct:
        shot = sct.grab({"left": 0, "top": 0, "width": 50, "height": 50})
        return any(b != 0 for b in shot.rgb[:150])


# ── Screenshot ───────────────────────────────────────────────────────────────

def take_screenshot(region: dict, output_path: Path) -> None:
    """Capture a screen region using macOS screencapture.

    Region coords are logical pixels (tkinter space).  screencapture accepts
    logical pixels and outputs at full native Retina resolution automatically,
    with no interaction with the Cocoa/CFRunLoop event system.
    """
    x, y, w, h = region["left"], region["top"], region["width"], region["height"]
    subprocess.run(
        ["/usr/sbin/screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(output_path)],
        check=True,
    )


# ── Capture window ────────────────────────────────────────────────────────────

class CaptureWindow:
    """
    Two-window capture UI:

    1. **Frame** — a standard macOS window (resizable via title bar) with low
       alpha (~0.2).  The user sees the textbook through it.  A bright green
       border drawn on its Canvas marks the capture boundary.
    2. **Bar** — a separate opaque Toplevel positioned directly below the frame.
       Contains Capture / Redo / Done buttons and a thumbnail of the last shot.

    On capture the frame goes fully transparent (alpha → 0) and the bar hides
    for ~100 ms so screencapture gets a clean image, then both reappear.

    All interaction is via tkinter — no input()/readline — so there is no
    CFRunLoop / Tcl notifier conflict.
    """

    _BORDER      = 4       # px — green border width
    _BTN_H       = 36      # px — button row height
    _STRIP_H     = 80      # px — overlap strip height (shows bottom of last capture)
    _FRAME_ALPHA = 0.20    # see-through but border still visible
    _BORDER_CLR  = "#00ff88"
    _BAR_BG      = "#111111"

    def run(self, session: Session) -> None:
        # ── frame window (semi-transparent, resizable) ────────────────────────
        frame = tk.Tk()
        frame.title(f"Capture — {session.title}")
        frame.configure(bg="black")
        frame.attributes("-topmost", True)
        frame.attributes("-alpha", self._FRAME_ALPHA)
        frame.geometry("820x600+120+80")
        frame.minsize(200, 150)

        canvas = tk.Canvas(frame, bg="black", highlightthickness=0)
        canvas.pack(fill=tk.BOTH, expand=True)

        # ── control bar (opaque, follows frame) ──────────────────────────────
        bar_total = self._BTN_H + self._STRIP_H
        bar = tk.Toplevel(frame)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bar.configure(bg=self._BAR_BG)

        # -- button row (top of bar) --
        btn_row = tk.Frame(bar, bg=self._BAR_BG, height=self._BTN_H)
        btn_row.pack(fill=tk.X, side=tk.TOP)
        btn_row.pack_propagate(False)

        btn_cap = tk.Button(
            btn_row, text="● Capture", bg="#1a5c2a", fg="#00ff88",
            relief=tk.FLAT, font=("Helvetica", 12, "bold"),
            activebackground="#2a8c3a", cursor="hand2",
            command=lambda: do_capture(),
        )
        btn_cap.pack(side=tk.LEFT, padx=(8, 4), pady=4)

        btn_redo = tk.Button(
            btn_row, text="↩ Redo", bg="#3a2a10", fg="#ffaa00",
            relief=tk.FLAT, font=("Helvetica", 11),
            activebackground="#5a4010", cursor="hand2",
            command=lambda: do_redo(),
        )
        btn_redo.pack(side=tk.LEFT, padx=4, pady=4)

        page_label = tk.Label(
            btn_row, bg=self._BAR_BG, fg="#00ff88",
            text=f"{session.page_count} pages",
            font=("Helvetica", 11, "bold"),
        )
        page_label.pack(side=tk.LEFT, padx=10)

        hint = tk.Label(
            btn_row, bg=self._BAR_BG, fg="#555555",
            text="Enter = capture  •  r = redo  •  q = done",
            font=("Helvetica", 10),
        )
        hint.pack(side=tk.LEFT, padx=4)

        btn_done = tk.Button(
            btn_row, text="✕ Done", bg="#3a1010", fg="#ff6666",
            relief=tk.FLAT, font=("Helvetica", 11),
            activebackground="#5a2020", cursor="hand2",
            command=lambda: do_quit(),
        )
        btn_done.pack(side=tk.RIGHT, padx=(4, 8), pady=4)

        # -- overlap strip (bottom of bar) — shows bottom slice of last capture --
        strip_frame = tk.Frame(bar, bg="#0a0a0a", height=self._STRIP_H)
        strip_frame.pack(fill=tk.BOTH, expand=True)
        strip_frame.pack_propagate(False)

        strip_hint = tk.Label(
            strip_frame, bg="#0a0a0a", fg="#333333",
            text="Last page overlap will appear here",
            font=("Helvetica", 10),
        )
        strip_hint.pack(expand=True)

        strip_label = tk.Label(strip_frame, bg="#0a0a0a")
        photo_ref: list = [None]

        # ── position the bar directly below the frame ─────────────────────────
        def reposition_bar(event: tk.Event | None = None) -> None:
            x = frame.winfo_rootx()
            y = frame.winfo_rooty() + frame.winfo_height()
            w = frame.winfo_width()
            bar.geometry(f"{w}x{bar_total}+{x}+{y}")
            bar.lift()

        frame.bind("<Configure>", lambda e: (redraw_border(e), reposition_bar(e)))
        frame.after(50, reposition_bar)

        # ── border drawing ────────────────────────────────────────────────────
        def redraw_border(event: tk.Event | None = None) -> None:
            canvas.delete("border")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w <= 1 or h <= 1:
                return
            b = self._BORDER
            c = self._BORDER_CLR
            canvas.create_rectangle(0,   0,   w,   b,   fill=c, outline="", tags="border")
            canvas.create_rectangle(0,   h-b, w,   h,   fill=c, outline="", tags="border")
            canvas.create_rectangle(0,   0,   b,   h,   fill=c, outline="", tags="border")
            canvas.create_rectangle(w-b, 0,   w,   h,   fill=c, outline="", tags="border")

        # ── helpers ───────────────────────────────────────────────────────────
        def get_region() -> dict:
            """Region inside the green border (logical pixels)."""
            b = self._BORDER
            return {
                "left":   canvas.winfo_rootx() + b,
                "top":    canvas.winfo_rooty() + b,
                "width":  canvas.winfo_width()  - 2 * b,
                "height": canvas.winfo_height() - 2 * b,
            }

        def show_overlap(path: Path | None) -> None:
            """Display the bottom ~1/8 of the given image in the overlap strip."""
            if path is None:
                strip_label.pack_forget()
                strip_hint.pack(expand=True)
                photo_ref[0] = None
                return
            try:
                img = Image.open(path)
                # Crop bottom 1/8 of the image
                slice_h = max(1, img.height // 8)
                bottom = img.crop((0, img.height - slice_h, img.width, img.height))
                # Scale to fit the strip area (full bar width, STRIP_H tall)
                bar_w = max(1, bar.winfo_width() - 4)
                ratio = min(bar_w / bottom.width, self._STRIP_H / bottom.height)
                tw = max(1, int(bottom.width * ratio))
                th = max(1, int(bottom.height * ratio))
                bottom = bottom.resize((tw, th), Image.LANCZOS)
                photo = ImageTk.PhotoImage(bottom)
                photo_ref[0] = photo
                strip_hint.pack_forget()
                strip_label.configure(image=photo)
                strip_label.pack(expand=True)
            except Exception:
                pass

        # ── actions ───────────────────────────────────────────────────────────
        capturing = [False]

        def do_capture(event: tk.Event | None = None) -> None:
            if capturing[0]:
                return
            region = get_region()
            if region["width"] < 50 or region["height"] < 50:
                return
            capturing[0] = True
            out = session.screenshots_dir() / session.next_filename()

            # Hide both windows so screencapture gets a clean image
            frame.attributes("-alpha", 0)
            bar.withdraw()
            frame.update_idletasks()

            def finish() -> None:
                take_screenshot(region, out)
                frame.attributes("-alpha", self._FRAME_ALPHA)
                bar.deiconify()
                bar.lift()
                show_overlap(out)
                page_label.configure(text=f"{session.page_count} pages")
                capturing[0] = False

            frame.after(120, finish)   # 120 ms for macOS compositor

        def do_redo(event: tk.Event | None = None) -> None:
            shots = sorted(session.screenshots_dir().glob("*.png"))
            if not shots:
                return
            shots[-1].unlink()
            remaining = sorted(session.screenshots_dir().glob("*.png"))
            show_overlap(remaining[-1] if remaining else None)
            page_label.configure(text=f"{session.page_count} pages")

        def do_quit(event: tk.Event | None = None) -> None:
            frame.quit()

        # ── key bindings (frame + bar) ────────────────────────────────────────
        for widget in (frame, canvas, bar):
            widget.bind("<Return>", do_capture)
            widget.bind("r", do_redo)
            widget.bind("R", do_redo)
            widget.bind("q", do_quit)
            widget.bind("Q", do_quit)
            widget.bind("<Escape>", do_quit)

        frame.focus_force()
        frame.mainloop()
        try:
            bar.destroy()
        except Exception:
            pass
        try:
            frame.destroy()
        except Exception:
            pass
