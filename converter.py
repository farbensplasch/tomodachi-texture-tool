from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import zstandard as zstd
from PIL import Image, ImageOps

from swizzle import nsw_swizzle, nsw_deswizzle

SWIZZLE_MODE = 4
ZSTD_LEVEL = 16

# File name templates per item type.
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

# Offsets in Player.sav where the 64-byte UTF-16LE name slots begin.
# Each slot is 64 bytes (= 32 UTF-16LE chars, null-padded).
# Slot index == UGC file ID (e.g. slot 2 == UgcGoods002).
# Confirmed by reversing Player.sav; remaining types not yet mapped.
NAME_TABLE_OFFSETS: dict[str, int] = {
    "goods": 0x000E8FFC,
    "food":  0x000FD61C,
}


# ── item info dataclass ────────────────────────────────────────────────────────

@dataclass
class ItemInfo:
    id: int
    name: str
    ugctex_path: Optional[Path] = field(default=None)
    thumb_path:  Optional[Path] = field(default=None)
    canvas_path: Optional[Path] = field(default=None)


# ── save-folder helpers ────────────────────────────────────────────────────────

def find_slot_dirs(save_dir: Path) -> list[Path]:
    """Return all numeric slot subdirs (0/, 1/, …) that contain a Ugc folder."""
    slots = []
    try:
        for d in sorted(save_dir.iterdir()):
            if d.is_dir() and d.name.isdigit() and (d / "Ugc").is_dir():
                slots.append(d)
    except OSError:
        pass
    return slots


def get_item_names(player_sav: Path, mode: str) -> dict[int, str]:
    """Read item names for *mode* from Player.sav.

    Returns a dict mapping item ID → name string.
    Falls back to an empty dict on any error.
    """
    offset = NAME_TABLE_OFFSETS.get(mode)
    if offset is None:
        return {}
    try:
        data = player_sav.read_bytes()
        names: dict[int, str] = {}
        for slot in range(100):
            off = offset + slot * 64
            if off + 64 > len(data):
                break
            raw = data[off: off + 64]
            name = raw.decode("utf-16-le").rstrip("\x00")
            if name:
                names[slot] = name
        return names
    except Exception:
        return {}


def get_items(slot_dir: Path, mode: str, names: dict[int, str]) -> list[ItemInfo]:
    """Return all existing items of *mode* found in *slot_dir*/Ugc, merged with *names*."""
    templates = ITEM_TYPES[mode]
    ugc_dir = slot_dir / "Ugc"
    prefix, suffix = templates["ugctex"].split("{id}")

    items: dict[int, ItemInfo] = {}
    try:
        for f in ugc_dir.glob(f"{prefix}*{suffix}"):
            id_str = f.name[len(prefix): len(f.name) - len(suffix)]
            if not id_str.isdigit():
                continue
            item_id = int(id_str)

            canvas_name = templates["canvas"].format(id=id_str)
            thumb_name  = templates["thumb"].format(id=id_str)
            canvas_p = ugc_dir / canvas_name
            thumb_p  = ugc_dir / thumb_name

            items[item_id] = ItemInfo(
                id=item_id,
                name=names.get(item_id, f"Item {id_str}"),
                ugctex_path=f,
                thumb_path=thumb_p  if thumb_p.exists()  else None,
                canvas_path=canvas_p if canvas_p.exists() else None,
            )
    except OSError:
        pass

    return sorted(items.values(), key=lambda x: x.id)


# ── texture decoding (for preview) ────────────────────────────────────────────

def _make_dds(data: bytes, w: int, h: int, fourcc: bytes) -> bytes:
    """Build a minimal DDS file header and prepend it to *data*."""
    hdr = bytearray(128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<I", hdr,  4, 124)
    struct.pack_into("<I", hdr,  8, 0x1 | 0x2 | 0x4 | 0x1000)
    struct.pack_into("<I", hdr, 12, h)
    struct.pack_into("<I", hdr, 16, w)
    struct.pack_into("<I", hdr, 20, len(data))
    struct.pack_into("<I", hdr, 28, 1)
    struct.pack_into("<I", hdr, 76, 32)
    struct.pack_into("<I", hdr, 80, 0x4)   # DDPF_FOURCC
    hdr[84:88] = fourcc
    struct.pack_into("<I", hdr, 108, 0x1000)
    return bytes(hdr) + data


def decode_thumb(thumb_path: Path) -> Optional[Image.Image]:
    """Decode a *_Thumb.ugctex.zs to a PIL Image (256×256 BC3/DXT5)."""
    try:
        raw = zstd.ZstdDecompressor().decompress(thumb_path.read_bytes())
        ds  = nsw_deswizzle(raw, (256, 256), (4, 4), 16, 3)
        dds = _make_dds(ds, 256, 256, b"DXT5")
        return Image.open(io.BytesIO(dds)).convert("RGBA")
    except Exception:
        return None


def decode_ugctex(ugctex_path: Path) -> Optional[Image.Image]:
    """Decode a .ugctex.zs to a PIL Image (512×512 BC1/DXT1, goods/clothes/etc.)."""
    try:
        raw = zstd.ZstdDecompressor().decompress(ugctex_path.read_bytes())
        ds  = nsw_deswizzle(raw, (512, 512), (4, 4), 8, 4)
        dds = _make_dds(ds, 512, 512, b"DXT1")
        return Image.open(io.BytesIO(dds)).convert("RGBA")
    except Exception:
        return None


# ── texture conversion ─────────────────────────────────────────────────────────

def png_to_canvas(img: Image.Image) -> bytes:
    """Convert a PIL image → raw swizzled CANVAS blob (256×256 RGBA)."""
    img = img.convert("RGBA")
    if img.size != (256, 256):
        img = ImageOps.fit(img, (256, 256), Image.LANCZOS)
    raw = img.tobytes("raw")
    return bytes(nsw_swizzle(raw, (256, 256), (1, 1), 4, SWIZZLE_MODE))


def png_to_ugctex(img: Image.Image) -> bytes:
    """Convert a PIL image → raw swizzled UGCTEX blob (512×512 DXT1)."""
    img = img.convert("RGBA")
    if img.size != (512, 512):
        img = ImageOps.fit(img, (512, 512), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="DDS", pixel_format="DXT1")
    dxt1_data = buf.getvalue()[128:]
    return bytes(nsw_swizzle(dxt1_data, (512, 512), (4, 4), 8, SWIZZLE_MODE))


def png_to_thumb(img: Image.Image) -> bytes:
    """Convert a PIL image → raw swizzled thumbnail blob (256×256 BC3/DXT5)."""
    img = img.convert("RGBA")
    if img.size != (256, 256):
        img = ImageOps.fit(img, (256, 256), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="DDS", pixel_format="DXT5")
    dxt5_data = buf.getvalue()[128:]
    return bytes(nsw_swizzle(dxt5_data, (256, 256), (4, 4), 16, 3))


def zstd_compress(data: bytes) -> bytes:
    return zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(data)


def convert_and_export(
    png_path: Path,
    output_dir: Path,
    item_id: int,
    mode: str,
    on_progress: Optional[Callable[[str, float], None]] = None,
) -> tuple[Path, Path, Path]:
    """PNG → CANVAS + UGCTEX + THUMB → ZSTD → files written to *output_dir*.

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


# ── legacy helper (still used by get_highest_id display) ──────────────────────

def get_highest_id(folder: Path, mode: str) -> Optional[int]:
    template = ITEM_TYPES[mode]["ugctex"]
    if "{id}" not in template:
        return None
    prefix, suffix = template.split("{id}")
    max_id = None
    try:
        for f in folder.glob(f"{prefix}*{suffix}"):
            id_part = f.name[len(prefix): len(f.name) - len(suffix)]
            if id_part.isdigit():
                n = int(id_part)
                if max_id is None or n > max_id:
                    max_id = n
    except OSError:
        pass
    return max_id
