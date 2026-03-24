"""Image loading, resizing, and BGR565 conversion for the PMR-171 LCD."""

from __future__ import annotations

import struct
import sys
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    pass

# Try numpy for fast pixel conversion (optional, ~10x faster).
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# Pillow resampling — compatible across versions.
try:
    _RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:
    _RESAMPLE = Image.LANCZOS  # type: ignore[attr-defined]

from .constants import SCREEN_W, SCREEN_H


# ---------------------------------------------------------------------------
# Pixel conversion
# ---------------------------------------------------------------------------
def rgb_to_bgr565(r: int, g: int, b: int) -> int:
    """Convert one RGB888 pixel to 16-bit BGR565.

    The PMR-171 LCD (LT7680/ST7789V) expects blue in the high bits
    and red in the low bits — the reverse of standard RGB565.
    """
    return ((b >> 3) << 11) | ((g >> 2) << 5) | (r >> 3)


def image_to_bgr565_le(img: Image.Image) -> bytes:
    """Convert a PIL RGB image to BGR565 little-endian byte array.

    Uses numpy when available for ~10x throughput on 320x240 images.
    """
    img = img.convert("RGB")

    if _HAS_NUMPY:
        arr = np.array(img, dtype=np.uint16)
        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
        val = ((b >> 3) << 11) | ((g >> 2) << 5) | (r >> 3)
        return val.astype("<u2").tobytes()

    # Pure-Python fallback.
    w, h = img.size
    raw = img.tobytes()  # R G B R G B ...
    data = bytearray(w * h * 2)
    for i in range(w * h):
        off = i * 3
        px = rgb_to_bgr565(raw[off], raw[off + 1], raw[off + 2])
        struct.pack_into("<H", data, i * 2, px)
    return bytes(data)


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------
def load_and_prepare(
    path: str,
    resize_mode: str = "fit",
    target_w: int = SCREEN_W,
    target_h: int = SCREEN_H,
    bg_rgb: tuple[int, int, int] = (0, 0, 0),
) -> Image.Image:
    """Load an image file and prepare it for the PMR-171 LCD.

    Parameters
    ----------
    path:
        Path to PNG / JPEG / BMP / etc.
    resize_mode:
        "fit"     — scale to fit, letterbox with *bg_rgb* (default)
        "fill"    — scale to cover, center-crop
        "stretch" — distort to exact target dimensions
        "none"    — keep original size (must fit within target)
    target_w, target_h:
        Output dimensions (default 320x240).
    bg_rgb:
        Background color for letterboxing.

    Returns
    -------
    A PIL Image in RGB mode with exact *target_w* x *target_h* size
    (except "none" mode which keeps the original dimensions).
    """
    img = Image.open(path)

    # Composite RGBA onto solid background.
    if img.mode == "RGBA":
        bg = Image.new("RGBA", img.size, (*bg_rgb, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
    else:
        img = img.convert("RGB")

    orig_w, orig_h = img.size

    if resize_mode == "none":
        if orig_w > target_w or orig_h > target_h:
            raise ValueError(
                f"Image {orig_w}x{orig_h} exceeds {target_w}x{target_h}. "
                f"Use a resize mode to auto-resize."
            )
        return img

    if resize_mode == "stretch":
        return img.resize((target_w, target_h), _RESAMPLE)

    if resize_mode == "fit":
        scale = min(target_w / orig_w, target_h / orig_h)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        img = img.resize((new_w, new_h), _RESAMPLE)
        canvas = Image.new("RGB", (target_w, target_h), bg_rgb)
        canvas.paste(
            img, ((target_w - new_w) // 2, (target_h - new_h) // 2)
        )
        return canvas

    if resize_mode == "fill":
        scale = max(target_w / orig_w, target_h / orig_h)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        img = img.resize((new_w, new_h), _RESAMPLE)
        x_off = (new_w - target_w) // 2
        y_off = (new_h - target_h) // 2
        return img.crop(
            (x_off, y_off, x_off + target_w, y_off + target_h)
        )

    raise ValueError(f"Unknown resize mode: {resize_mode!r}")
