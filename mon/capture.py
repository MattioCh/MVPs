"""Screen capture. Returns an in-memory PNG (bytes) for the primary display.

Screenshots are NOT persisted to disk. macOS requires Screen Recording permission
for the terminal/IDE running this process.
"""

from __future__ import annotations

import io

import mss
from PIL import Image


def capture_primary_screen(max_width: int = 1280) -> bytes:
    """Grab the primary monitor, downscale to max_width, return PNG bytes."""
    with mss.mss() as sct:
        # monitors[0] is "all monitors", monitors[1] is the primary display.
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
