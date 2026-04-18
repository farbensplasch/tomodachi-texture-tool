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
# {id} is replaced with the zero-padded ID.
ITEM_TYPES: dict[str, dict[str, str]] = {
    "facepaint": {
        "canvas": "UgcFacePaint{id}.canvas.zs",
        "ugctex": "UgcFacePaint{id}.ugctex.zs",
        "thumb":  "UgcFacePaint{id}_Thumb.ugctex.zs",
    },
    "goods": {
        "canvas": "UgcGoods{id}.canvas.zs",
        "ugctex": "UgcGoods{id}.ugctex.zs",
        "thumb":  "UgcGoods{id}_Thumb.ugctex.zs",
    },
    "clothes": {
        "canvas": "UgcCloth{id}.canvas.zs",
        "ugctex": "UgcCloth{id}.ugctex.zs",
        "thumb":  "UgcCloth{id}_Thumb.ugctex.zs",
    },
    "exterior": {
        "canvas": "UgcExterior{id}.canvas.zs",
        "ugctex": "UgcExterior{id}.ugctex.zs",
        "thumb":  "UgcExterior{id}_Thumb.ugctex.zs",
    },
    "interior": {
        "canvas": "UgcInterior{id}.canvas.zs",
        "ugctex": "UgcInterior{id}.ugctex.zs",
        "thumb":  "UgcInterior{id}_Thumb.ugctex.zs",
    },
    "mapobject": {
        "canvas": "UgcMapObject{id}.canvas.zs",
        "ugctex": "UgcMapObject{id}.ugctex.zs",
        "thumb":  "UgcMapObject{id}_Thumb.ugctex.zs",
    },
    "mapfloor": {
        "canvas": "UgcMapFloor{id}.canvas.zs",
        "ugctex": "UgcMapFloor{id}.ugctex.zs",
        "thumb":  "UgcMapFloor{id}_Thumb.ugctex.zs",
    },
    "food": {
        "canvas": "UgcFood{id}.canvas.zs",
        "ugctex": "UgcFood{id}.ugctex.zs",
        "thumb":  "UgcFood{id}_Thumb.ugctex.zs",
    },
}


def png_to_canvas(img: Image.Image) -> bytes:
    """Convert a PIL image to a raw swizzled CANVAS blob (256x256 RGBA)."""
    img = img.convert("RGBA")
    if img.size != (256, 256):
        img = ImageOps.fit(img, (256, 256), Image.LANCZOS)
    raw = img.tobytes("raw")
    return bytes(nsw_swizzle(raw, (256, 256), (1, 1), 4, SWIZZLE_MODE))


def png_to_ugctex(img: Image.Image) -> bytes:
    """Convert a PIL image to a raw swizzled UGCTEX blob (512x512 DXT1)."""
    img = img.convert("RGBA")
    if img.size != (512, 512):
        img = ImageOps.fit(img, (512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="DDS", pixel_format="DXT1")
    dxt1_data = buf.getvalue()[128:]  # strip 128-byte DDS header
    return bytes(nsw_swizzle(dxt1_data, (512, 512), (4, 4), 8, SWIZZLE_MODE))


def png_to_thumb(img: Image.Image) -> bytes:
    """Convert a PIL image to a raw swizzled thumbnail blob (128x128 RGBA).

    The game writes a *_Thumb.ugctex.zs alongside every .canvas.zs / .ugctex.zs
    pair.  Without it the game considers the item incomplete and removes all
    three texture files on the next load.
    """
    img = img.convert("RGBA")
    if img.size != (128, 128):
        img = ImageOps.fit(img, (128, 128), Image.LANCZOS)
    raw = img.tobytes("raw")
    return bytes(nsw_swizzle(raw, (128, 128), (1, 1), 4, SWIZZLE_MODE))


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
    on_progress: Callable[[str, float], None] | None = None,
) -> tuple[Path, Path, Path]:
    """
    Full pipeline: PNG → CANVAS + UGCTEX + THUMB → ZSTD → files in output_dir.

    Returns (canvas_path, ugctex_path, thumb_path).
    """
    templates = ITEM_TYPES[mode]
    id_str = str(item_id).zfill(3)

    def progress(msg: str, pct: float):
        if on_progress:
            on_progress(msg, pct)

    progress("Loading image…", 0.05)
    img = Image.open(png_path)

    progress("Converting to CANVAS…", 0.20)
    canvas_data = png_to_canvas(img.copy())

    progress("Converting to UGCTEX…", 0.45)
    ugctex_data = png_to_ugctex(img.copy())

    progress("Converting to thumbnail…", 0.65)
    thumb_data = png_to_thumb(img.copy())

    progress("Compressing (ZSTD)…", 0.80)
    canvas_zs = zstd_compress(canvas_data)
    ugctex_zs = zstd_compress(ugctex_data)
    thumb_zs  = zstd_compress(thumb_data)

    progress("Writing files…", 0.95)
    output_dir.mkdir(parents=True, exist_ok=True)

    canvas_path = output_dir / templates["canvas"].format(id=id_str)
    ugctex_path = output_dir / templates["ugctex"].format(id=id_str)
    thumb_path  = output_dir / templates["thumb"].format(id=id_str)

    canvas_path.write_bytes(canvas_zs)
    ugctex_path.write_bytes(ugctex_zs)
    thumb_path.write_bytes(thumb_zs)

    progress("Done!", 1.0)
    return canvas_path, ugctex_path, thumb_path
