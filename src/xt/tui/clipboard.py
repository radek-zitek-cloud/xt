"""The system clipboard for the TUI's text boxes (card #110): copy writes to it, ctrl+v reads it.

Tried in order: Wayland (wl-copy/wl-paste), X11 (xclip, xsel), macOS (pbcopy/pbpaste). When none
works, the caller says so; it never falls back to a private clipboard without telling.
"""

import shutil
import subprocess

COPY = [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"], ["pbcopy"]]
PASTE = [["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"],
         ["xsel", "--clipboard", "--output"], ["pbpaste"]]


def copy(text: str) -> bool:
    for argv in COPY:
        if shutil.which(argv[0]):
            try:
                # no captured output: wl-copy stays in the background to serve the clipboard and
                # would hold captured pipes open until the timeout
                if subprocess.run(argv, input=text, text=True, timeout=5, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL).returncode == 0:
                    return True
            except (OSError, subprocess.TimeoutExpired):
                continue
    return False


def paste() -> str | None:
    for argv in PASTE:
        if shutil.which(argv[0]):
            try:
                p = subprocess.run(argv, text=True, timeout=5, capture_output=True)
            except (OSError, subprocess.TimeoutExpired):
                continue
            if p.returncode == 0:
                return p.stdout
    return None
