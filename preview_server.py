"""
Preview window subprocess for textbook2audiobook.

Runs as a separate process so it owns the Tk main thread and CFRunLoop
entirely — no competing readline/input() or signal handlers.

Protocol (stdin, one line per message):
  <absolute path>  — display this image
  CLEAR            — show "No capture yet" placeholder
  QUIT             — close the window and exit

Usage:
  python preview_server.py left,top,width,height
  (coords in logical pixels)
"""
from __future__ import annotations

import select
import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(1)

    left, top, width, height = map(int, sys.argv[1].split(","))
    region = {"left": left, "top": top, "width": width, "height": height}

    PW = 300

    root = tk.Tk()
    root.title("Last Capture")
    root.attributes("-topmost", True)
    root.configure(bg="#1a1a1a")

    log_w = root.winfo_screenwidth()
    log_h = root.winfo_screenheight()

    cap_cx = region["left"] + region["width"]  / 2
    cap_cy = region["top"]  + region["height"] / 2

    wx = log_w - PW - 10 if cap_cx < log_w / 2 else 10
    wy = log_h - 240 - 40 if cap_cy < log_h / 2 else 10

    root.geometry(f"{PW}x240+{wx}+{wy}")
    root.lift()
    root.focus_force()

    label = tk.Label(
        root, bg="#1a1a1a", fg="#555555",
        text="No capture yet", font=("Helvetica", 11),
    )
    label.pack(fill=tk.BOTH, expand=True)
    photo_ref: list = [None]

    def poll() -> None:
        try:
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable:
                line = sys.stdin.readline()
                if not line:          # EOF — parent closed stdin
                    root.quit()
                    return
                line = line.strip()
                if line == "QUIT":
                    root.quit()
                    return
                elif line == "CLEAR":
                    label.configure(image="", text="No capture yet", fg="#555555")
                    photo_ref[0] = None
                elif line:
                    img = Image.open(line)
                    img.thumbnail((PW, 220), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    photo_ref[0] = photo
                    label.configure(image=photo, text="")
        except Exception:
            pass
        root.after(100, poll)

    root.after(100, poll)
    root.mainloop()
    try:
        root.destroy()
    except Exception:
        pass


if __name__ == "__main__":
    main()
