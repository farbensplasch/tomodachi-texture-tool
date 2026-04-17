from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

import zstandard as zstd
from PIL import Image, ImageOps

from swizzle import nsw_swizzle

SWIZZLE_MODE = 4
ZSTD_LEVEL = 16

# File name templates per item type.
# {id} is replaced with the zero-padded ID; omitting {id} means no ID in that filename.
ITEM_TYPES: dict[str, dict[str, str]] = {
    "facepaint": {"canvas": "UgcFacePaint{id}.canvas.zs",  "ugctex": "UgcFacePaint{id}.ugctex.zs"},
    "goods":     {"canvas": "UgcGoods{id}.canvas.zs",      "ugctex": "UgcGoods{id}.ugctex.zs"},
    "clothes":   {"canvas": "UgcCloth{id}.canvas.zs",      "ugctex": "UgcCloth{id}.ugctex.zs"},
    "exterior":  {"canvas": "UgcExterior{id}.canvas.zs",   "ugctex": "UgcExterior{id}.ugctex.zs"},
    "interior":  {"canvas": "UgcInterior{id}.canvas.zs",   "ugctex": "UgcInterior{id}.ugctex.zs"},
    "mapobject": {"canvas": "UgcMapObject{id}.canvas.zs",  "ugctex": "UgcMapObject{id}.ugctex.zs"},
    "mapfloor":  {"canvas": "UgcMapFloor{id}.canvas.zs",   "ugctex": "UgcMapFloor{id}.ugctex.zs"},
    "food":      {"canvas": "UgcFood{id}.canvas.zs",       "ugctex": "UgcFood{id}.ugctex.zs"},
}


def _gamma(img: Image.Image, gamma: float) -> Image.Image:
    return img.point(lambda x: ((x / 255) ** gamma) * 255)


def png_to_canvas(img: Image.Image, use_srgb: bool, resize_mode: int) -> bytes:
    """Convert a PIL image to a raw swizzled CANVAS blob (256x256 RGBA)."""
    img = img.convert("RGBA")
    if img.size != (256, 256):
        if resize_mode == 1:
            img = img.resize((256, 256), Image.LANCZOS)
        else:
            img = ImageOps.fit(img, (256, 256), Image.LANCZOS)

    if not use_srgb:
        img = _gamma(img, 2.2)

    img = img.convert("RGBA")
    raw = img.tobytes("raw")
    return bytes(nsw_swizzle(raw, (256, 256), (1, 1), 4, SWIZZLE_MODE))


def png_to_ugctex(img: Image.Image, use_srgb: bool, resize_mode: int) -> bytes:
    """Convert a PIL image to a raw swizzled UGCTEX blob (512x512 DXT1)."""
    img = img.convert("RGBA")
    if img.size != (512, 512):
        if resize_mode == 1:
            img = img.resize((512, 512), Image.LANCZOS)
        else:
            img = ImageOps.fit(img, (512, 512), Image.LANCZOS)

    if not use_srgb:
        img = _gamma(img, 2.2)

    buf = io.BytesIO()
    img.save(buf, format="DDS", pixel_format="DXT1")
    dxt1_data = buf.getvalue()[128:]  # strip 128-byte DDS header

    return bytes(nsw_swizzle(dxt1_data, (512, 512), (4, 4), 8, SWIZZLE_MODE))


def get_highest_id(folder: Path, mode: str) -> int | None:
    """Return the highest numeric ID found in folder for the given mode, or None."""
    template = ITEM_TYPES[mode]["ugctex"]  # ugctex always contains {id}
    if "{id}" not in template:
        return None
    prefix, suffix = template.split("{id}")
    max_id = None
    for f in folder.glob(f"{prefix}*{suffix}"):
        id_part = f.name[len(prefix): len(f.name) - len(suffix)]
        if id_part.isdigit():
            n = int(id_part)
            if max_id is None or n > max_id:
                max_id = n
    return max_id


def zstd_compress(data: bytes) -> bytes:
    return zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(data)


def convert_and_export(
    png_path: Path,
    output_dir: Path,
    item_id: int,
    mode: str,
    use_srgb: bool = False,
    resize_mode: int = 1,
    on_progress: Callable[[str, float], None] | None = None,
) -> tuple[Path, Path]:
    """
    Full pipeline: PNG → CANVAS + UGCTEX → ZSTD → renamed files in output_dir.

    Returns (canvas_path, ugctex_path).
    """
    templates = ITEM_TYPES[mode]
    id_str = str(item_id).zfill(3)

    def progress(msg: str, pct: float):
        if on_progress:
            on_progress(msg, pct)

    progress("Loading image…", 0.05)
    img = Image.open(png_path)

    progress("Converting to CANVAS…", 0.2)
    canvas_data = png_to_canvas(img.copy(), use_srgb, resize_mode)

    progress("Converting to UGCTEX…", 0.5)
    ugctex_data = png_to_ugctex(img.copy(), use_srgb, resize_mode)

    progress("Compressing (ZSTD)…", 0.8)
    canvas_zs = zstd_compress(canvas_data)
    ugctex_zs = zstd_compress(ugctex_data)

    progress("Writing files…", 0.95)
    output_dir.mkdir(parents=True, exist_ok=True)

    canvas_path = output_dir / templates["canvas"].format(id=id_str)
    ugctex_path = output_dir / templates["ugctex"].format(id=id_str)

    canvas_path.write_bytes(canvas_zs)
    ugctex_path.write_bytes(ugctex_zs)

    progress("Done!", 1.0)
    return canvas_path, ugctex_path
