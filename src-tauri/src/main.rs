#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod converter;

use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::Serialize;
use tauri::{Emitter, Manager};

#[derive(Serialize, Clone)]
struct ProgressEvent {
    step: String,
    pct:  f64,
}

// ─── Window controls ──────────────────────────────────────────────────────────

#[tauri::command]
fn close_app(app: tauri::AppHandle) {
    app.exit(0);
}

#[tauri::command]
fn minimize_app(window: tauri::WebviewWindow) {
    window.minimize().ok();
}

// ─── File dialogs ─────────────────────────────────────────────────────────────

#[tauri::command]
async fn select_png(app: tauri::AppHandle) -> Option<serde_json::Value> {
    use tauri_plugin_dialog::DialogExt;
    let raw = app.dialog().file().add_filter("PNG Image", &["png"]).blocking_pick_file()?;
    let path_buf = raw.simplified().into_path().ok()?;
    let path_str = path_buf.to_string_lossy().into_owned();
    let data    = std::fs::read(&path_buf).ok()?;
    let preview = format!("data:image/png;base64,{}", STANDARD.encode(&data));
    Some(serde_json::json!({ "path": path_str, "preview": preview }))
}

#[tauri::command]
async fn select_folder(app: tauri::AppHandle) -> Option<String> {
    use tauri_plugin_dialog::DialogExt;
    let raw = app.dialog().file().blocking_pick_folder()?;
    raw.simplified().into_path().ok().map(|p| p.to_string_lossy().into_owned())
}

// ─── Emulator auto-detection ─────────────────────────────────────────────────

#[tauri::command]
fn find_emulator_saves() -> Vec<converter::FoundSave> {
    converter::find_emulator_saves()
}

// ─── Texture slot scanning ────────────────────────────────────────────────────

#[derive(Serialize)]
struct TextureSlotsResult {
    slots: Vec<converter::SlotInfo>,
}

#[tauri::command]
async fn get_texture_slots(save_folder: String, item_type: String) -> TextureSlotsResult {
    tokio::task::spawn_blocking(move || {
        let slots = converter::scan_save_slots(std::path::Path::new(&save_folder), &item_type);
        TextureSlotsResult { slots }
    })
    .await
    .unwrap_or(TextureSlotsResult { slots: vec![] })
}

// ─── Export slot texture ─────────────────────────────────────────────────────

#[tauri::command]
async fn export_slot_texture(
    app: tauri::AppHandle,
    save_folder: String,
    item_type: String,
    item_id: u32,
) -> Result<String, String> {
    use tauri_plugin_dialog::DialogExt;

    // Decode the texture first so we know it works before asking where to save
    let png_bytes = tokio::task::spawn_blocking({
        let sf = save_folder.clone();
        let it = item_type.clone();
        move || converter::export_slot_texture(std::path::Path::new(&sf), &it, item_id)
    })
    .await
    .map_err(|e| e.to_string())??;

    // Ask user where to save
    let default_name = format!("{item_type}_{item_id:03}.png");
    let save_path = app
        .dialog()
        .file()
        .set_file_name(&default_name)
        .add_filter("PNG Image", &["png"])
        .blocking_save_file();

    let Some(raw) = save_path else {
        return Err("cancelled".into());
    };
    let path_buf = raw.simplified().into_path().map_err(|e| e.to_string())?;
    std::fs::write(&path_buf, &png_bytes).map_err(|e| e.to_string())?;
    Ok(path_buf.to_string_lossy().into_owned())
}

// ─── Preview from path (used by drag & drop) ─────────────────────────────────

#[tauri::command]
async fn preview_png(path: String) -> Option<serde_json::Value> {
    let path_buf = std::path::PathBuf::from(&path);
    let data     = std::fs::read(&path_buf).ok()?;
    let preview  = format!("data:image/png;base64,{}", STANDARD.encode(&data));
    Some(serde_json::json!({ "path": path, "preview": preview }))
}

// ─── Backup listing & restore ────────────────────────────────────────────────

#[tauri::command]
fn list_backups(save_folder: String) -> Vec<converter::BackupInfo> {
    converter::list_backups(std::path::Path::new(&save_folder))
}

#[tauri::command]
fn restore_backup(save_folder: String, backup_path: String) -> Result<(), String> {
    converter::restore_backup(
        std::path::Path::new(&save_folder),
        std::path::Path::new(&backup_path),
    )
}

// ─── Conversion ───────────────────────────────────────────────────────────────

#[tauri::command]
async fn convert_texture(
    window: tauri::WebviewWindow,
    png_path: String,
    save_folder: String,
    item_type: String,
    item_id: u32,
    alpha_threshold: u8,
    scale_mode_name: String,
) -> Result<converter::ConvertResult, String> {
    let win = window.clone();

    let scale_mode: converter::ScaleMode = scale_mode_name
    .parse()
    .unwrap_or(converter::ScaleMode::Lanczos3);

    tokio::task::spawn_blocking(move || {
        converter::convert(
            std::path::Path::new(&png_path),
            std::path::Path::new(&save_folder),
            &item_type,
            item_id,
            |step, pct| {
                win.emit("progress", ProgressEvent { step: step.to_string(), pct }).ok();
            },
            alpha_threshold,
            scale_mode,
            
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

// ─── Entry point ─────────────────────────────────────────────────────────────

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            close_app,
            minimize_app,
            select_png,
            select_folder,
            find_emulator_saves,
            get_texture_slots,
            convert_texture,
            list_backups,
            restore_backup,
            preview_png,
            export_slot_texture,
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").unwrap();
            #[cfg(target_os = "windows")]
            { use window_vibrancy::apply_acrylic; apply_acrylic(&window, Some((15, 8, 32, 120))).ok(); }
            #[cfg(target_os = "macos")]
            { use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial}; apply_vibrancy(&window, NSVisualEffectMaterial::HudWindow, None, None).ok(); }
            #[cfg(target_os = "linux")]
            { use window_vibrancy::apply_blur; apply_blur(&window, Some((15, 8, 32, 120))).ok(); }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
