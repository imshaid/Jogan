#!/usr/bin/env python3
"""Web icons from the owner's logo (docs/brand/jogan-light.png).

The logo is the mark (yellow and blue arrow) above the Bangla wordmark, on a near-white
background. Icons use the mark alone, because the wordmark cannot be read at 16-32 px; the
header writes "Jogan · যোগান" as text next to it. The background is removed by un-blending
each pixel from white, so anti-aliased edges stay smooth on any tab colour.

Run: ``uv run --with pillow python scripts/brand_icons.py`` (Pillow is not a project
dependency; the outputs are committed).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "brand" / "jogan-light.png"
MARK_BOX = (205, 114, 691, 590)  # left, top, right, bottom of the mark, measured on the source
SOLID = 243.0  # 255 minus the smallest channel of the mark's solid blue: fully opaque from here


def transparent(im: Image.Image) -> Image.Image:
    """Alpha from the distance to white (smallest channel), colours un-blended from white."""
    rgb = np.asarray(im.convert("RGB")).astype(float)
    alpha = np.clip((255.0 - rgb.min(axis=2)) / SOLID, 0.0, 1.0)
    alpha[alpha < 0.03] = 0.0  # paper noise of the scan-like background
    safe = np.maximum(alpha, 1e-6)[..., None]
    colour = np.clip((rgb - 255.0 * (1.0 - alpha[..., None])) / safe, 0.0, 255.0)
    out = np.dstack([colour, alpha * 255.0]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def square(im: Image.Image, pad: float, background: tuple[int, ...]) -> Image.Image:
    """Centre ``im`` on a square canvas with ``pad`` (share of the side) on every edge."""
    side = round(max(im.size) / (1.0 - 2.0 * pad))
    canvas = Image.new("RGBA", (side, side), background)
    canvas.alpha_composite(im, ((side - im.width) // 2, (side - im.height) // 2))
    return canvas


def resized(im: Image.Image, size: int) -> Image.Image:
    return im.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    mark = transparent(Image.open(SOURCE).crop(MARK_BOX))
    clear = square(mark, 0.02, (0, 0, 0, 0))
    app, public = ROOT / "web" / "app", ROOT / "web" / "public" / "brand"
    public.mkdir(parents=True, exist_ok=True)
    out = {
        "favicon": app / "favicon.ico",
        "icon": app / "icon.png",
        "apple": app / "apple-icon.png",
        "header": public / "jogan-mark.png",
    }
    resized(clear, 48).save(out["favicon"], sizes=[(16, 16), (32, 32), (48, 48)])
    resized(clear, 192).save(out["icon"], optimize=True)
    # Apple touch icons are shown opaque; give the mark a white tile with a margin
    tile = square(mark, 0.14, (255, 255, 255, 255)).convert("RGB")
    resized(tile, 180).save(out["apple"], optimize=True)
    resized(clear, 128).save(out["header"], optimize=True)
    for p in out.values():
        print(f"{p.relative_to(ROOT)}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
