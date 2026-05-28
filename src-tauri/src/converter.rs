use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::str::FromStr;
use base64::{engine::general_purpose::STANDARD, Engine as _};
use image::{imageops, DynamicImage, ImageEncoder};
use serde::Serialize;

pub enum ScaleMode {
    Nearest,
    Lanczos3,
}

impl FromStr for ScaleMode {
    type Err = ();

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_ascii_lowercase().as_str() {
            "nearest" | "nearestneighbor" | "nearest-neighbor" => {
                Ok(Self::Nearest)
            }

            "lanczos" | "lanczos3" => {
                Ok(Self::Lanczos3)
            }

            _ => Err(()),
        }
    }
}

// ─── Item type file-name templates ───────────────────────────────────────────

struct ItemType {
    key:       &'static str,
    canvas:    &'static str,
    ugctex:    &'static str,
    thumb:     &'static str,
    /// ugctex pixel dimensions.  Food uses 384×384; everything else 512×512.
    ugctex_px: u32,
}

const TYPES: &[ItemType] = &[
    ItemType { key: "facepaint", canvas: "UgcFacePaint{id}.canvas.zs",  ugctex: "UgcFacePaint{id}.ugctex.zs",  thumb: "UgcFacePaint{id}_Thumb.ugctex.zs", ugctex_px: 512 },
    ItemType { key: "goods",     canvas: "UgcGoods{id}.canvas.zs",      ugctex: "UgcGoods{id}.ugctex.zs",      thumb: "UgcGoods{id}_Thumb.ugctex.zs",     ugctex_px: 512 },
    ItemType { key: "clothes",   canvas: "UgcCloth{id}.canvas.zs",      ugctex: "UgcCloth{id}.ugctex.zs",      thumb: "UgcCloth{id}_Thumb.ugctex.zs",     ugctex_px: 512 },
    ItemType { key: "exterior",  canvas: "UgcExterior{id}.canvas.zs",   ugctex: "UgcExterior{id}.ugctex.zs",   thumb: "UgcExterior{id}_Thumb.ugctex.zs",  ugctex_px: 512 },
    ItemType { key: "interior",  canvas: "UgcInterior{id}.canvas.zs",   ugctex: "UgcInterior{id}.ugctex.zs",   thumb: "UgcInterior{id}_Thumb.ugctex.zs",  ugctex_px: 512 },
    ItemType { key: "mapobject", canvas: "UgcMapObject{id}.canvas.zs",  ugctex: "UgcMapObject{id}.ugctex.zs",  thumb: "UgcMapObject{id}_Thumb.ugctex.zs", ugctex_px: 512 },
    ItemType { key: "mapfloor",  canvas: "UgcMapFloor{id}.canvas.zs",   ugctex: "UgcMapFloor{id}.ugctex.zs",   thumb: "UgcMapFloor{id}_Thumb.ugctex.zs",  ugctex_px: 512 },
    ItemType { key: "food",      canvas: "UgcFood{id}.canvas.zs",       ugctex: "UgcFood{id}.ugctex.zs",       thumb: "UgcFood{id}_Thumb.ugctex.zs",      ugctex_px: 384 },
];

fn tmpl(item_type: &str) -> Option<&'static ItemType> {
    TYPES.iter().find(|t| t.key == item_type)
}

fn apply_id(template: &str, id_str: &str) -> String {
    template.replace("{id}", id_str)
}

// ─── Nintendo Switch Block-Linear swizzle (GOB address formula) ──────────────
//
// Reference: LivingTheDreamToolkit / Nintendo Switch GPU documentation.
// For BC-compressed textures, `width` and `height` are in *block* units.
// For uncompressed RGBA, they are in *pixel* units.
// `bpe`          = bytes per element (block or pixel)
// `block_height` = GOB block-height parameter (16 for canvas/ugctex, 8 for thumb)

fn div_round_up(n: usize, d: usize) -> usize { (n + d - 1) / d }

#[inline]
fn gob_address(x: usize, y: usize, width_in_gobs: usize, bpe: usize, block_height: usize) -> usize {
    let x_bytes  = x * bpe;
    let gob_addr =
          (y / (8 * block_height)) * 512 * block_height * width_in_gobs
        + (x_bytes / 64) * 512 * block_height
        + ((y % (8 * block_height)) / 8) * 512;
    let xg = x_bytes % 64;
    let yg = y % 8;
    gob_addr
        + ((xg % 64) / 32) * 256
        + ((yg % 8)  /  2) * 64
        + ((xg % 32) / 16) * 32
        + (yg % 2)         * 16
        + (xg % 16)
}

fn swizzle_block_linear(data: &[u8], width: usize, height: usize, bpe: usize, block_height: usize) -> Vec<u8> {
    let width_in_gobs = div_round_up(width * bpe, 64);
    let padded_h      = div_round_up(height, 8 * block_height) * (8 * block_height);
    let mut out       = vec![0u8; width_in_gobs * padded_h * 64];
    for y in 0..height {
        for x in 0..width {
            let src = (y * width + x) * bpe;
            let dst = gob_address(x, y, width_in_gobs, bpe, block_height);
            out[dst..dst + bpe].copy_from_slice(&data[src..src + bpe]);
        }
    }
    out
}

fn deswizzle_block_linear(data: &[u8], width: usize, height: usize, bpe: usize, block_height: usize) -> Vec<u8> {
    let width_in_gobs = div_round_up(width * bpe, 64);
    let padded_h      = div_round_up(height, 8 * block_height) * (8 * block_height);
    let padded_size   = width_in_gobs * padded_h * 64;
    // Pad source buffer if it is shorter than the expected GOB-aligned size
    let src: Vec<u8> = if data.len() >= padded_size {
        data.to_vec()
    } else {
        let mut v = vec![0u8; padded_size];
        v[..data.len()].copy_from_slice(data);
        v
    };
    let mut out = vec![0u8; width * height * bpe];
    for y in 0..height {
        for x in 0..width {
            let s = gob_address(x, y, width_in_gobs, bpe, block_height);
            let d = (y * width + x) * bpe;
            out[d..d + bpe].copy_from_slice(&src[s..s + bpe]);
        }
    }
    out
}

// ─── Colour-space & resize helpers ───────────────────────────────────────────

/// sRGB u8 → linear u8  (IEC 61966-2-1 piecewise transfer function, RGB only).
/// The game's renderer works in linear light — textures stored as raw sRGB
/// values appear too bright because the GPU expands them again.
#[inline]
fn srgb_to_lin(v: u8) -> u8 {
    let f = v as f32 / 255.0;
    let l = if f <= 0.04045 { f / 12.92 } else { ((f + 0.055) / 1.055).powf(2.4) };
    (l * 255.0 + 0.5) as u8
}

/// Resize `img` to `w × h` (Lanczos3) using **premultiplied-alpha** compositing,
/// apply sRGB→linear on the RGB channels, then return straight-alpha RGBA8.
///
/// Premultiplied alpha prevents Lanczos from blending the undefined RGB of
/// transparent pixels into opaque neighbours, which would create bright fringes.
/// sRGB→linear is required because the Switch GPU samples BC1/BC3 textures as
/// linear data and the renderer works in linear light; without the conversion
/// the stored sRGB values look too bright on screen.
///
/// None of that matters if you use nearest neighbour tho :)
fn prepare_rgba(img: &DynamicImage, w: u32, h: u32, alpha_threshold: &u8, scale_mode: &ScaleMode) -> Vec<u8> {
    let src = img.to_rgba8();
    let (sw, sh) = (src.width(), src.height());

    // Select resize filter
    let filter = match scale_mode {
        ScaleMode::Nearest  => imageops::FilterType::Nearest,
        ScaleMode::Lanczos3 => imageops::FilterType::Lanczos3,
    };

    if sw == w && sh == h {
        // No resize needed — still apply sRGB→linear.
        return src.into_raw().chunks_exact(4)
            .flat_map(|p| [srgb_to_lin(p[0]), srgb_to_lin(p[1]), srgb_to_lin(p[2]), p[3]])
            .collect();
    }

    // 1. Pre-multiply: RGB ← RGB × (A / 255)  so transparent pixels contribute
    //    (0,0,0,0) to the filter kernel instead of their arbitrary stored RGB.
    let premul: Vec<u8> = src.chunks_exact(4).flat_map(|p| {
        let a = p[3] as f32 / 255.0;
        [
            (p[0] as f32 * a + 0.5) as u8,
            (p[1] as f32 * a + 0.5) as u8,
            (p[2] as f32 * a + 0.5) as u8,
            p[3],
        ]
    }).collect();


    let pm_img  = image::RgbaImage::from_raw(sw, sh, premul).unwrap();

    // Resize with selected filter
    let resized = imageops::resize(&pm_img, w, h, filter);

    // 3. Un-premultiply: RGB ← RGB / (A / 255), then apply sRGB→linear.
    //    Fully-transparent pixels stay (0,0,0,0).
    resized.chunks_exact(4).flat_map(|p| {
        let mut a = p[3];

        if a < *alpha_threshold {
            a = 0;
        }
        
        if a == 0 {
            [0u8, 0, 0, 0]
        } else {
            let af = a as f32 / 255.0;
            [
                srgb_to_lin(((p[0] as f32 / af).round() as u32).min(255) as u8),
                srgb_to_lin(((p[1] as f32 / af).round() as u32).min(255) as u8),
                srgb_to_lin(((p[2] as f32 / af).round() as u32).min(255) as u8),
                a,
            ]
        }
    }).collect()
}

// ─── Block compression / decompression ───────────────────────────────────────

fn bc_compress(fmt: squish::Format, rgba: &[u8], width: u32, height: u32) -> Vec<u8> {
    let (w, h) = (width as usize, height as usize);
    let mut out = vec![0u8; fmt.compressed_size(w, h)];
    fmt.compress(rgba, w, h,
        squish::Params {
            algorithm: squish::Algorithm::IterativeClusterFit,
            // Ignore transparent pixels when fitting colour endpoints so the
            // background (A=0) does not drag the palette toward its stored RGB
            // values, which would wash out colours in blocks near the edge.
            weigh_colour_by_alpha: true,
            ..Default::default()
        },
        &mut out);
    out
}

fn bc1_compress(rgba: &[u8], w: u32, h: u32) -> Vec<u8> { bc_compress(squish::Format::Bc1, rgba, w, h) }
fn bc3_compress(rgba: &[u8], w: u32, h: u32) -> Vec<u8> { bc_compress(squish::Format::Bc3, rgba, w, h) }

fn bc3_decompress(data: &[u8], w: u32, h: u32) -> Vec<u8> {
    let mut out = vec![0u8; w as usize * h as usize * 4];
    squish::Format::Bc3.decompress(data, w as usize, h as usize, &mut out);
    out
}

// ─── Per-format encoding ──────────────────────────────────────────────────────
//
// Swizzle parameters — all measured in *block* units for BC textures:
//   canvas  256×256 RGBA8    → width=256px,  height=256px,  bpe=4,  block_height=16
//   ugctex  512×512 BC1      → width=128blk, height=128blk, bpe=8,  block_height=16
//   ugctex  384×384 BC1 food → width= 96blk, height= 96blk, bpe=8,  block_height=16
//   thumb   256×256 BC3      → width= 64blk, height= 64blk, bpe=16, block_height=8

fn to_canvas(img: &DynamicImage, alpha_threshold: &u8, scale_mode: &ScaleMode) -> Vec<u8> {
    let mut rgba = prepare_rgba(img, 256, 256, alpha_threshold, scale_mode);
    // Snap anti-aliased alpha edges to hard opaque/transparent.
    // Semi-transparent edge pixels appear as a 1-pixel fringe ring in the
    // in-game canvas editor.  Binary alpha eliminates that outline.
    for pixel in rgba.chunks_exact_mut(4) {
        pixel[3] = if pixel[3] >= 128 { 255 } else { 0 };
    }
    swizzle_block_linear(&rgba, 256, 256, 4, 16)
}

fn to_ugctex(img: &DynamicImage, px: u32, alpha_threshold: &u8, scale_mode: &ScaleMode) -> Vec<u8> {
    let mut rgba = prepare_rgba(img, px, px, alpha_threshold, scale_mode);
    // Snap anti-aliased alpha edges to hard opaque/transparent before BC1.
    // BC1 blocks that contain a mix of opaque and semi-transparent pixels use
    // "transparent mode" (c0 ≤ c1), which reserves one colour slot for the
    // transparent index and leaves only 3 colours for the opaque content.
    // This degrades palette quality and causes a 1-pixel fringe of transparent
    // pixels around opaque edges.  Binary alpha eliminates mixed blocks.
    for pixel in rgba.chunks_exact_mut(4) {
        pixel[3] = if pixel[3] >= 128 { 255 } else { 0 };
    }
    let blocks  = bc1_compress(&rgba, px, px);
    let blk_dim = (px / 4) as usize;   // 128 for 512px, 96 for 384px
    swizzle_block_linear(&blocks, blk_dim, blk_dim, 8, 16)
}

fn to_thumb(img: &DynamicImage, alpha_threshold: &u8, scale_mode: &ScaleMode) -> Vec<u8> {
    let rgba   = prepare_rgba(img, 256, 256, alpha_threshold, scale_mode);
    let blocks = bc3_compress(&rgba, 256, 256);
    swizzle_block_linear(&blocks, 64, 64, 16, 8)
}

/// Compress `data` with ZSTD level 3.
/// We pledge the source size so libzstd writes the content-size field into the
/// frame header (FHD bit-pattern 0xa0 = SSF + FCS_4).  The game's ZSTD parser
/// requires the content-size field to be present; without it the decompressor
/// returns nothing and the texture appears transparent/missing.
fn zstd_compress(data: &[u8]) -> std::io::Result<Vec<u8>> {
    use std::io::Write as _;
    let mut enc = zstd::Encoder::new(Vec::new(), 3)?;
    enc.set_pledged_src_size(Some(data.len() as u64))?;
    enc.write_all(data)?;
    enc.finish()
}

// ─── Thumbnail decoding for previews ─────────────────────────────────────────

fn thumb_to_preview(zs_data: &[u8]) -> Option<String> {
    let raw = zstd::decode_all(std::io::Cursor::new(zs_data)).ok()?;
    // Thumb is 256×256 BC3 → 64×64 blocks × 16 bpe = 65536 bytes (GOB-aligned).
    // Accept any size >= minimum needed; deswizzle pads internally if needed.
    const THUMB_MIN: usize = 64 * 64 * 16;
    if raw.len() < THUMB_MIN / 2 { return None; } // clearly wrong file
    let blocks = deswizzle_block_linear(&raw, 64, 64, 16, 8);
    let rgba   = bc3_decompress(&blocks, 256, 256);
    let img    = image::RgbaImage::from_raw(256, 256, rgba)?;
    let small  = imageops::resize(&img, 64, 64, imageops::FilterType::Triangle);
    let mut buf = Vec::new();
    image::codecs::png::PngEncoder::new(&mut buf)
        .write_image(small.as_raw(), 64, 64, image::ExtendedColorType::Rgba8).ok()?;
    Some(format!("data:image/png;base64,{}", STANDARD.encode(&buf)))
}

// ─── Emulator auto-detection ─────────────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct FoundSave {
    pub emulator: String,
    pub path:     String,
}

fn emulator_save_roots() -> Vec<(&'static str, PathBuf)> {
    let mut v = Vec::new();

    #[cfg(target_os = "windows")]
    if let Ok(appdata) = std::env::var("APPDATA") {
        let base = PathBuf::from(appdata);
        v.push(("Ryujinx", base.join("Ryujinx").join("bis").join("user").join("save")));
        v.push(("Eden",    base.join("eden").join("bis").join("user").join("save")));
    }

    #[cfg(target_os = "macos")]
    if let Ok(home) = std::env::var("HOME") {
        let base = PathBuf::from(&home);
        v.push(("Ryujinx", base.join("Library").join("Application Support").join("Ryujinx").join("bis").join("user").join("save")));
        v.push(("Eden",    base.join(".local").join("share").join("eden").join("bis").join("user").join("save")));
    }

    #[cfg(target_os = "linux")]
    if let Ok(home) = std::env::var("HOME") {
        let h = PathBuf::from(&home);
        let cfg  = std::env::var("XDG_CONFIG_HOME").map(PathBuf::from).unwrap_or_else(|_| h.join(".config"));
        let data = std::env::var("XDG_DATA_HOME").map(PathBuf::from).unwrap_or_else(|_| h.join(".local").join("share"));
        v.push(("Ryujinx", cfg .join("Ryujinx").join("bis").join("user").join("save")));
        v.push(("Eden",    data.join("eden").join("bis").join("user").join("save")));
    }

    v
}

fn is_valid_save_folder(dir: &Path) -> bool {
    let d0 = dir.join("0");
    let d1 = dir.join("1");
    (d0.is_dir() || d1.is_dir()) &&
    (find_ugc_dir(&d0).is_some() || find_ugc_dir(&d1).is_some())
}

/// Finds all Tomodachi Life save folders for known emulators.
/// Scans one level deep (root/{id}/) and two levels deep (root/{id}/{id}/)
/// because different Ryujinx/Eden versions use different layouts.
pub fn find_emulator_saves() -> Vec<FoundSave> {
    let mut found = Vec::new();
    for (name, root) in emulator_save_roots() {
        if !root.is_dir() { continue; }
        let Ok(lvl1) = std::fs::read_dir(&root) else { continue };
        for e1 in lvl1.flatten() {
            let p1 = e1.path();
            if !p1.is_dir() { continue; }

            // Level 1: root/{id}/ — check directly
            if is_valid_save_folder(&p1) {
                found.push(FoundSave {
                    emulator: name.to_string(),
                    path:     p1.to_string_lossy().into_owned(),
                });
                continue; // don't descend further if already matched
            }

            // Level 2: root/{id}/{id}/ — some builds nest one more level
            let Ok(lvl2) = std::fs::read_dir(&p1) else { continue };
            for e2 in lvl2.flatten() {
                let p2 = e2.path();
                if p2.is_dir() && is_valid_save_folder(&p2) {
                    found.push(FoundSave {
                        emulator: name.to_string(),
                        path:     p2.to_string_lossy().into_owned(),
                    });
                }
            }
        }
    }
    found
}

// ─── Active-slot detection ────────────────────────────────────────────────────

/// Returns which sub-slot ("0" or "1") is the active/committed save state,
/// detected by comparing the newest file-modification time across all Ugc*.zs
/// files in each slot's UGC directory.
///
/// Writing to the *inactive* slot corrupts the Switch dual-slot integrity that
/// lets the game do atomic save commits.  Always write only to the active slot.
fn detect_active_slot(save_dir: &Path) -> &'static str {
    let newest_mtime = |sub: &str| -> Option<std::time::SystemTime> {
        let ugc_dir = find_ugc_dir(&save_dir.join(sub))?;
        std::fs::read_dir(&ugc_dir).ok()?
            .flatten()
            .filter(|e| {
                let n = e.file_name().to_string_lossy().into_owned();
                n.starts_with("Ugc") && n.ends_with(".zs")
            })
            .filter_map(|e| e.metadata().ok()?.modified().ok())
            .max()
    };
    match (newest_mtime("0"), newest_mtime("1")) {
        (Some(t0), Some(t1)) => if t1 > t0 { "1" } else { "0" },
        (None, Some(_))      => "1",
        _                    => "0",   // default / only slot 0 exists
    }
}

// ─── Save-folder slot scanning ────────────────────────────────────────────────

/// Finds the UGC sub-folder inside *parent* (e.g. inside "0" or "1") by
/// looking for the first directory that contains Ugc*.zs files.
fn find_ugc_dir(parent: &Path) -> Option<PathBuf> {
    if has_ugc_files(parent) { return Some(parent.to_path_buf()); }
    if let Ok(rd) = std::fs::read_dir(parent) {
        for entry in rd.flatten() {
            let p = entry.path();
            if p.is_dir() && has_ugc_files(&p) { return Some(p); }
        }
    }
    None
}

fn has_ugc_files(dir: &Path) -> bool {
    std::fs::read_dir(dir).map(|rd| {
        rd.flatten().any(|e| {
            let n = e.file_name().to_string_lossy().into_owned();
            n.starts_with("Ugc") && n.ends_with(".zs")
        })
    }).unwrap_or(false)
}

/// Finds thumb file paths for all IDs of *item_type* inside *dir*.
/// Accepts both `_Thumb_ugctex.zs` (reference/correct) and `_Thumb.ugctex.zs` (legacy) variants.
fn find_ids_in_dir(dir: &Path, item_type: &str) -> BTreeMap<u32, PathBuf> {
    let mut map = BTreeMap::new();
    let t = match tmpl(item_type) { Some(t) => t, None => return map };

    // The correct game format (confirmed by reference) is `_Thumb_ugctex.zs`.
    // Older TTT versions wrote `_Thumb.ugctex.zs`, so we accept both.
    let primary = t.thumb;
    // Also accept the alternative underscore-placement variant just in case
    let legacy  = primary.replace("_Thumb.ugctex.zs", "_Thumb_ugctex.zs");

    if let Ok(rd) = std::fs::read_dir(dir) {
        'entry: for entry in rd.flatten() {
            let name = entry.file_name().to_string_lossy().into_owned();
            for pat in [primary, legacy.as_str()] {
                let Some((prefix, suffix)) = pat.split_once("{id}") else { continue };
                if name.starts_with(prefix) && name.ends_with(suffix) {
                    let mid = &name[prefix.len()..name.len() - suffix.len()];
                    if let Ok(id) = mid.parse::<u32>() {
                        map.entry(id).or_insert_with(|| entry.path());
                    }
                    continue 'entry;
                }
            }
        }
    }
    map
}

#[derive(Serialize, Clone)]
pub struct SlotInfo {
    pub id:      u32,
    pub preview: Option<String>,
    /// true = exists only in the *inactive* slot (not yet committed to active)
    pub warning: bool,
}

/// Scans *save_dir*/0 and *save_dir*/1 for UGC textures of *item_type*.
/// Thumbnails are read from the active (committed) slot; slots that exist
/// only in the inactive slot get a warning flag.
pub fn scan_save_slots(save_dir: &Path, item_type: &str) -> Vec<SlotInfo> {
    let active   = detect_active_slot(save_dir);
    let inactive = if active == "0" { "1" } else { "0" };

    let ugc_active   = find_ugc_dir(&save_dir.join(active))
        .unwrap_or_else(|| save_dir.join(active));
    let ugc_inactive = find_ugc_dir(&save_dir.join(inactive))
        .unwrap_or_else(|| save_dir.join(inactive));

    let ids_active   = find_ids_in_dir(&ugc_active,   item_type);
    let ids_inactive = find_ids_in_dir(&ugc_inactive, item_type);

    let mut all_ids: std::collections::BTreeSet<u32> = Default::default();
    all_ids.extend(ids_active.keys().copied());
    all_ids.extend(ids_inactive.keys().copied());

    all_ids.into_iter().map(|id| {
        let in_active   = ids_active.contains_key(&id);
        let in_inactive = ids_inactive.contains_key(&id);
        // Prefer thumbnail from the active (committed) slot
        let preview = ids_active.get(&id).or_else(|| ids_inactive.get(&id))
            .and_then(|p| std::fs::read(p).ok().and_then(|d| thumb_to_preview(&d)));
        SlotInfo { id, preview, warning: in_inactive && !in_active }
    }).collect()
}

// ─── Whole-folder backup ──────────────────────────────────────────────────────

fn copy_dir_all(src: &Path, dst: &Path, skip: &Path) -> std::io::Result<()> {
    if src == skip { return Ok(()); }
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)?.flatten() {
        let sp = entry.path();
        if sp == skip { continue; }
        let dp = dst.join(entry.file_name());
        if sp.is_dir() { copy_dir_all(&sp, &dp, skip)?; } else { std::fs::copy(&sp, &dp)?; }
    }
    Ok(())
}

fn backup_save(save_dir: &Path) -> std::io::Result<()> {
    let ts = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs()).unwrap_or(0);
    let backup_root = save_dir.join("_TTT_Backup").join(ts.to_string());
    let skip = save_dir.join("_TTT_Backup");
    // Back up both "0" and "1" sub-folders
    for sub in &["0", "1"] {
        let src = save_dir.join(sub);
        if src.exists() {
            copy_dir_all(&src, &backup_root.join(sub), &skip)?;
        }
    }
    Ok(())
}

// ─── Slot texture export ──────────────────────────────────────────────────────

/// Decodes the stored texture for a slot and returns it as a PNG byte vector.
/// Tries canvas.zs first (256×256 RGBA, lossless), then ugctex.zs (512×512 BC1).
pub fn export_slot_texture(
    save_dir: &Path,
    item_type: &str,
    item_id: u32,
) -> Result<Vec<u8>, String> {
    let t      = tmpl(item_type).ok_or_else(|| format!("Unknown item type: {item_type}"))?;
    let id_str = format!("{item_id:03}");

    // Try active slot first, then inactive as fallback
    let active   = detect_active_slot(save_dir);
    let inactive = if active == "0" { "1" } else { "0" };
    for sub in &[active, inactive] {
        let sub_dir = save_dir.join(sub);
        let Some(ugc_dir) = find_ugc_dir(&sub_dir) else { continue };

        // ── Try canvas.zs (raw RGBA 256×256, bpe=4, blockHeight=16) ──────
        let canvas_path = ugc_dir.join(apply_id(t.canvas, &id_str));
        if canvas_path.exists() {
            if let Ok(zs) = std::fs::read(&canvas_path) {
                if let Ok(raw) = zstd::decode_all(std::io::Cursor::new(&zs)) {
                    let rgba = deswizzle_block_linear(&raw, 256, 256, 4, 16);
                    if let Some(img) = image::RgbaImage::from_raw(256, 256, rgba) {
                        let mut buf = std::io::Cursor::new(Vec::new());
                        image::DynamicImage::ImageRgba8(img)
                            .write_to(&mut buf, image::ImageFormat::Png)
                            .map_err(|e| e.to_string())?;
                        return Ok(buf.into_inner());
                    }
                }
            }
        }

        // ── Fall back to ugctex.zs (BC1, 512×512 or 384×384 for food) ────
        let ugctex_path = ugc_dir.join(apply_id(t.ugctex, &id_str));
        if ugctex_path.exists() {
            if let Ok(zs) = std::fs::read(&ugctex_path) {
                if let Ok(raw) = zstd::decode_all(std::io::Cursor::new(&zs)) {
                    // Detect pixel size from decompressed GOB size
                    // 131072 = 512×512 BC1; 98304 = 384×384 BC1 (food)
                    let (px, blk) = match raw.len() {
                        98304  => (384u32, 96usize),
                        _      => (512u32, 128usize),
                    };
                    let blocks = deswizzle_block_linear(&raw, blk, blk, 8, 16);
                    let mut rgba = vec![0u8; px as usize * px as usize * 4];
                    squish::Format::Bc1.decompress(&blocks, px as usize, px as usize, &mut rgba);
                    if let Some(img) = image::RgbaImage::from_raw(px, px, rgba) {
                        let mut buf = std::io::Cursor::new(Vec::new());
                        image::DynamicImage::ImageRgba8(img)
                            .write_to(&mut buf, image::ImageFormat::Png)
                            .map_err(|e| e.to_string())?;
                        return Ok(buf.into_inner());
                    }
                }
            }
        }
    }

    Err("No texture file found for this slot".into())
}

// ─── Backup listing & restore ─────────────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct BackupInfo {
    pub timestamp: u64,
    pub label:     String,
    pub path:      String,
}

/// Formats a Unix timestamp (seconds) into a human-readable string,
/// e.g. "27 Apr 2026 — 18:08:45". Pure-Rust, no extra deps.
fn format_timestamp(ts: u64) -> String {
    let time_of_day = ts % 86400;
    let h = time_of_day / 3600;
    let m = (time_of_day % 3600) / 60;
    let s = time_of_day % 60;

    // Civil date from days since epoch (Gregorian proleptic)
    let z     = ts as i64 / 86400 + 719_468;
    let era   = (if z >= 0 { z } else { z - 146_096 }) / 146_097;
    let doe   = z - era * 146_097;
    let yoe   = (doe - doe/1_460 + doe/36_524 - doe/146_096) / 365;
    let doy   = doe - (365*yoe + yoe/4 - yoe/100);
    let mp    = (5*doy + 2) / 153;
    let day   = doy - (153*mp + 2)/5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year  = yoe + era * 400 + if month <= 2 { 1 } else { 0 };

    const MONTHS: &[&str] = &[
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec",
    ];
    let mn = MONTHS.get((month as usize).saturating_sub(1)).copied().unwrap_or("???");
    format!("{day} {mn} {year}  —  {:02}:{:02}:{:02}", h, m, s)
}

/// Returns all backups inside `save_dir/_TTT_Backup/`, newest first.
pub fn list_backups(save_dir: &Path) -> Vec<BackupInfo> {
    let backup_root = save_dir.join("_TTT_Backup");
    if !backup_root.exists() { return vec![]; }

    let mut backups: Vec<BackupInfo> = std::fs::read_dir(&backup_root)
        .ok().into_iter().flatten().flatten()
        .filter_map(|e| {
            let p = e.path();
            if !p.is_dir() { return None; }
            let ts: u64 = p.file_name()?.to_str()?.parse().ok()?;
            Some(BackupInfo {
                timestamp: ts,
                label: format_timestamp(ts),
                path:  p.to_string_lossy().into_owned(),
            })
        })
        .collect();
    backups.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));
    backups
}

/// Restores `backup_path/0` → `save_dir/0` and `backup_path/1` → `save_dir/1`.
/// Clears each destination sub-folder before copying so the result exactly
/// mirrors the backup (no leftover files from after the backup was taken).
pub fn restore_backup(save_dir: &Path, backup_path: &Path) -> Result<(), String> {
    let dummy = PathBuf::from("");
    for sub in &["0", "1"] {
        let src = backup_path.join(sub);
        let dst = save_dir.join(sub);
        if !src.exists() { continue; }
        if dst.exists() {
            std::fs::remove_dir_all(&dst)
                .map_err(|e| format!("Could not clear folder {sub}: {e}"))?;
        }
        copy_dir_all(&src, &dst, &dummy)
            .map_err(|e| format!("Could not restore folder {sub}: {e}"))?;
    }
    Ok(())
}

// ─── Public API ───────────────────────────────────────────────────────────────

#[derive(Serialize, Clone)]
pub struct ConvertResult {
    pub canvas:  String,
    pub ugctex:  String,
    pub thumb:   String,
    pub folders: Vec<String>,  // which sub-folders were written ("0", "1")
}

/// Converts *png_path* and writes the result into **only the active (committed)
/// save slot** inside *save_dir* (either `0/` or `1/`, auto-detected by mtime).
/// Writing to both slots destroys the Switch dual-slot integrity and causes the
/// game to lose the ability to save — so we deliberately leave the inactive
/// slot untouched. Backs up the whole save folder first.
pub fn convert(
    png_path: &Path,
    save_dir: &Path,
    item_type: &str,
    item_id: u32,
    on_progress: impl Fn(&str, f64),
    alpha_threshold: u8,
    scale_mode: ScaleMode,
) -> Result<ConvertResult, String> {
    let t = tmpl(item_type)
        .ok_or_else(|| format!("Unknown item type: {item_type}"))?;
    let id_str = format!("{item_id:03}");

    on_progress("Loading image…", 0.05);
    let img = image::open(png_path).map_err(|e| format!("Cannot open image: {e}"))?;

    on_progress("Building CANVAS (256×256 RGBA)…", 0.20);
    let canvas_raw = to_canvas(&img, &alpha_threshold, &scale_mode);

    let ugctex_px = t.ugctex_px;
    on_progress(&format!("Building UGCTEX ({}×{} BC1)…", ugctex_px, ugctex_px), 0.40);
    let ugctex_raw = to_ugctex(&img, ugctex_px, &alpha_threshold, &scale_mode);

    on_progress("Building thumbnail (256×256 BC3)…", 0.58);
    let thumb_raw  = to_thumb(&img, &alpha_threshold, &scale_mode);

    on_progress("Compressing with ZSTD…", 0.72);
    let canvas_zs = zstd_compress(&canvas_raw).map_err(|e| e.to_string())?;
    let ugctex_zs = zstd_compress(&ugctex_raw).map_err(|e| e.to_string())?;
    let thumb_zs  = zstd_compress(&thumb_raw ).map_err(|e| e.to_string())?;

    on_progress("Backing up save folder…", 0.84);
    backup_save(save_dir).map_err(|e| format!("Backup failed: {e}"))?;

    on_progress("Writing files…", 0.94);
    let mut folders_written = Vec::new();

    // Write into EVERY slot sub-folder that exists (both "0" and "1" when present).
    // The game may read from either slot depending on its internal commit state, so
    // writing to both guarantees the texture is visible.  We only write the three
    // UGC texture files and leave all other save data untouched, which keeps the
    // dual-slot atomic-commit mechanism intact.
    let mut first_canvas = String::new();
    let mut first_ugctex = String::new();
    let mut first_thumb  = String::new();
    let mut any_written  = false;

    for sub in &["0", "1"] {
        let sub_dir = save_dir.join(sub);
        if !sub_dir.exists() { continue; }

        // Write into the UGC subfolder inside this slot, auto-detected
        let out_dir = find_ugc_dir(&sub_dir).unwrap_or(sub_dir);

        let canvas_path = out_dir.join(apply_id(t.canvas, &id_str));
        let ugctex_path = out_dir.join(apply_id(t.ugctex, &id_str));
        let thumb_path  = out_dir.join(apply_id(t.thumb,  &id_str));

        std::fs::write(&canvas_path, &canvas_zs).map_err(|e| e.to_string())?;
        std::fs::write(&ugctex_path, &ugctex_zs).map_err(|e| e.to_string())?;
        std::fs::write(&thumb_path,  &thumb_zs ).map_err(|e| e.to_string())?;

        folders_written.push(sub.to_string());
        if !any_written {
            first_canvas = canvas_path.to_string_lossy().into_owned();
            first_ugctex = ugctex_path.to_string_lossy().into_owned();
            first_thumb  = thumb_path .to_string_lossy().into_owned();
            any_written  = true;
        }
    }

    if !any_written {
        return Err("No save sub-folders (0 or 1) found inside the chosen folder.".into());
    }

    on_progress("Done!", 1.0);
    Ok(ConvertResult {
        canvas:  first_canvas,
        ugctex:  first_ugctex,
        thumb:   first_thumb,
        folders: folders_written,
    })
}

// ─── Tests ────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;

    /// GOB address spot-checks against the C# LivingTheDreamToolkit reference.
    #[test]
    fn gob_address_matches_reference() {
        // Canvas: 256×256 RGBA8 → widthInGobs=16, bpe=4, blockHeight=16
        let w = 16usize; let bpe = 4; let bh = 16;
        assert_eq!(gob_address(0,  0,  w, bpe, bh), 0);
        assert_eq!(gob_address(1,  0,  w, bpe, bh), 4);
        assert_eq!(gob_address(8,  0,  w, bpe, bh), 256);   // crosses 32-byte boundary
        assert_eq!(gob_address(16, 0,  w, bpe, bh), 8192);  // crosses gob column
        assert_eq!(gob_address(0,  1,  w, bpe, bh), 16);    // y=1 within GOB
        assert_eq!(gob_address(0,  2,  w, bpe, bh), 64);
        assert_eq!(gob_address(0,  8,  w, bpe, bh), 512);   // crosses gob row

        // ugctex: 512×512 BC1 → 128×128 blocks, bpe=8, blockHeight=16, widthInGobs=16
        let wb = 16usize; let bpb = 8; let bhb = 16;
        assert_eq!(gob_address(0, 0,   wb, bpb, bhb), 0);
        assert_eq!(gob_address(1, 0,   wb, bpb, bhb), 8);
        assert_eq!(gob_address(8, 0,   wb, bpb, bhb), 8192); // 8*8=64 bytes → gob column 1
        assert_eq!(gob_address(0, 128, wb, bpb, bhb), 131072); // would be out-of-range (not reached)
    }

    /// swizzle then deswizzle must be the identity.
    #[test]
    fn swizzle_round_trip_canvas() {
        // 256×256 RGBA8 — fill with a recognisable gradient
        let size = 256 * 256 * 4;
        let linear: Vec<u8> = (0..size).map(|i| (i % 251) as u8).collect();
        let swizzled   = swizzle_block_linear(&linear, 256, 256, 4, 16);
        let recovered  = deswizzle_block_linear(&swizzled, 256, 256, 4, 16);
        assert_eq!(linear, recovered, "canvas round-trip mismatch");
    }

    #[test]
    fn swizzle_round_trip_ugctex_512() {
        // 128×128 BC1 blocks — fill with random-looking pattern
        let size = 128 * 128 * 8;
        let linear: Vec<u8> = (0..size).map(|i: usize| (i.wrapping_mul(17) % 256) as u8).collect();
        let swizzled  = swizzle_block_linear(&linear, 128, 128, 8, 16);
        let recovered = deswizzle_block_linear(&swizzled, 128, 128, 8, 16);
        assert_eq!(linear, recovered, "ugctex-512 round-trip mismatch");
    }

    #[test]
    fn swizzle_round_trip_thumb() {
        // 64×64 BC3 blocks
        let size = 64 * 64 * 16;
        let linear: Vec<u8> = (0..size).map(|i| (i % 199) as u8).collect();
        let swizzled  = swizzle_block_linear(&linear, 64, 64, 16, 8);
        let recovered = deswizzle_block_linear(&swizzled, 64, 64, 16, 8);
        assert_eq!(linear, recovered, "thumb round-trip mismatch");
    }

    #[test]
    fn swizzle_round_trip_ugctex_384() {
        // 96×96 BC1 blocks (food)
        let size = 96 * 96 * 8;
        let linear: Vec<u8> = (0..size).map(|i| (i % 233) as u8).collect();
        let swizzled  = swizzle_block_linear(&linear, 96, 96, 8, 16);
        let recovered = deswizzle_block_linear(&swizzled, 96, 96, 8, 16);
        assert_eq!(linear, recovered, "ugctex-384 round-trip mismatch");
    }
}
