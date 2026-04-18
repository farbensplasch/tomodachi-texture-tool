from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog
from typing import Optional

import customtkinter as ctk
from PIL import Image

import converter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── colour palette ─────────────────────────────────────────────────────────────
BG      = "#0b0b10"
SURF    = "#14141f"
SURF2   = "#1c1c2a"
SURF_SEL= "#252540"   # selected item row
BORDER  = "#26263a"
ACCENT  = "#7c6af6"
ACCENTH = "#6a58e0"
SUCCESS = "#34d399"
ERROR   = "#fb7185"
FG      = "#dde0f5"
MUTED   = "#4e4e70"
MUTED2  = "#8282a8"

PREVIEW_W = 172   # texture preview box inner width  (px)
PREVIEW_H = 172   # texture preview box inner height (px)


# ── tiny helpers ───────────────────────────────────────────────────────────────

def _lbl(parent, text, size=12, weight="normal", color=FG, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight=weight), **kw)


def _row(parent) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color="transparent")


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=SURF, corner_radius=14,
                        border_width=1, border_color=BORDER, **kw)


def _divider(parent):
    ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(fill="x")


# ── main window ────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    MODES = ["Facepaint", "Goods", "Clothes", "Exterior",
             "Interior", "MapObject", "MapFloor", "Food"]

    def __init__(self):
        super().__init__()
        self.title("Tomodachi Texture Tool")
        self.geometry("700x680")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        # ── state ──────────────────────────────────────────────────────────────
        self._save_dir:   Optional[Path]             = None
        self._slot_dirs:  list[Path]                 = []
        self._items:      list[converter.ItemInfo]   = []
        self._selected:   Optional[converter.ItemInfo] = None
        self._png_path:   Optional[Path]             = None
        self._converting: bool                       = False
        self._item_rows:  dict[int, ctk.CTkFrame]    = {}
        self._img_refs:   list                       = []   # keep CTkImage refs alive

        self._build()
        self._try_enable_dnd()

    # ══════════════════════════════════════════════════════════════════════════
    # BUILD
    # ══════════════════════════════════════════════════════════════════════════

    def _build(self):
        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(14, 10))

        self._build_folder_card(body)
        self._build_content(body)
        self._build_bottom(body)

        _lbl(body, "made by farbensplasch", size=10, color=MUTED).pack(
            anchor="e", pady=(4, 0))

    # ── header bar ─────────────────────────────────────────────────────────────

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=SURF, corner_radius=0, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkFrame(hdr, fg_color=ACCENT, corner_radius=0, width=4).pack(
            side="left", fill="y")
        _lbl(hdr, "Tomodachi Texture Tool", size=15, weight="bold").pack(
            side="left", padx=16)
        _lbl(hdr, "v1.2", size=11, color=MUTED).pack(side="right", padx=18)

    # ── save-folder + item-type card ───────────────────────────────────────────

    def _build_folder_card(self, parent):
        card = _card(parent)
        card.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        # Save folder row
        r1 = _row(inner)
        r1.pack(fill="x", pady=(0, 8))
        _lbl(r1, "Save Folder", size=11, color=MUTED2, width=86, anchor="w").pack(side="left")
        self._folder_var = ctk.StringVar()
        self._folder_entry = ctk.CTkEntry(
            r1, textvariable=self._folder_var,
            placeholder_text="e.g. …/save/0000000000000005",
            fg_color=SURF2, border_color=BORDER,
            text_color=FG, placeholder_text_color=MUTED,
            font=ctk.CTkFont(size=11),
        )
        self._folder_entry.pack(side="left", fill="x", expand=True)
        self._folder_entry.bind("<Return>", lambda _: self._on_save_folder_changed())
        ctk.CTkButton(
            r1, text="Browse", width=72, height=30,
            fg_color=SURF2, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            text_color=MUTED2, font=ctk.CTkFont(size=11),
            command=self._browse_save_folder,
        ).pack(side="left", padx=(8, 0))

        # Item type row
        r2 = _row(inner)
        r2.pack(fill="x")
        _lbl(r2, "Item Type", size=11, color=MUTED2, width=86, anchor="w").pack(side="left")
        self._mode_var = ctk.StringVar(value="Goods")
        ctk.CTkOptionMenu(
            r2, values=self.MODES, variable=self._mode_var,
            command=lambda _: self._refresh_items(),
            font=ctk.CTkFont(size=12),
            fg_color=SURF2, button_color=ACCENT, button_hover_color=ACCENTH,
            dropdown_fg_color=SURF2, dropdown_hover_color=ACCENT,
            text_color=FG, dropdown_text_color=FG,
            width=170,
        ).pack(side="left")
        self._slot_lbl = _lbl(r2, "", size=11, color=MUTED2)
        self._slot_lbl.pack(side="left", padx=(14, 0))

    # ── two-column content ─────────────────────────────────────────────────────

    def _build_content(self, parent):
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="both", expand=True, pady=(0, 10))
        content.columnconfigure(0, minsize=216)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_item_list(content)
        self._build_editor(content)

    # ── left: item list ────────────────────────────────────────────────────────

    def _build_item_list(self, parent):
        card = _card(parent)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))
        _lbl(header, "Items", size=12, weight="bold").pack(side="left")
        self._item_count_lbl = _lbl(header, "", size=10, color=MUTED2)
        self._item_count_lbl.pack(side="right")

        _divider(card)

        self._item_scroll = ctk.CTkScrollableFrame(
            card, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        self._item_scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self._empty_lbl = _lbl(
            self._item_scroll,
            "No items found.\nCreate items in-game first,\nthen refresh.",
            size=11, color=MUTED, justify="center",
        )
        self._empty_lbl.pack(pady=24)

    # ── right: editor ──────────────────────────────────────────────────────────

    def _build_editor(self, parent):
        card = _card(parent)
        card.grid(row=0, column=1, sticky="nsew")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        # ── preview row (current  →  new) ─────────────────────────────────────
        prev_row = ctk.CTkFrame(inner, fg_color="transparent")
        prev_row.pack(fill="x")
        prev_row.columnconfigure(0, weight=1)
        prev_row.columnconfigure(1, minsize=32)
        prev_row.columnconfigure(2, weight=1)

        # Current texture box
        self._cur_box, self._cur_img_lbl, self._cur_caption = \
            self._make_preview_box(prev_row, "Current")
        self._cur_box.grid(row=0, column=0, sticky="nsew")

        # Arrow
        _lbl(prev_row, "→", size=22, color=MUTED).grid(row=0, column=1)

        # New texture box (clickable)
        self._new_box, self._new_img_lbl, self._new_caption = \
            self._make_preview_box(prev_row, "New", clickable=True)
        self._new_box.grid(row=0, column=2, sticky="nsew")

        # ── item name label ────────────────────────────────────────────────────
        self._item_name_lbl = _lbl(inner, "← select an item from the list",
                                   size=12, color=MUTED)
        self._item_name_lbl.pack(anchor="w", pady=(12, 6))

        # ── browse button ──────────────────────────────────────────────────────
        self._browse_btn = ctk.CTkButton(
            inner, text="Browse PNG…",
            height=32, font=ctk.CTkFont(size=12),
            fg_color=SURF2, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            text_color=MUTED2, state="disabled",
            command=self._browse_png,
        )
        self._browse_btn.pack(fill="x", pady=(0, 8))

        # ── replace button ─────────────────────────────────────────────────────
        self._replace_btn = ctk.CTkButton(
            inner, text="Replace Texture",
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENTH, text_color="#ffffff",
            corner_radius=10, state="disabled",
            command=self._on_replace,
        )
        self._replace_btn.pack(fill="x")

    def _make_preview_box(
        self, parent, title: str, clickable: bool = False
    ) -> tuple[ctk.CTkFrame, ctk.CTkLabel, ctk.CTkLabel]:
        """Return (frame, image_label, caption_label)."""
        box = ctk.CTkFrame(
            parent, fg_color=SURF2, corner_radius=10,
            border_width=1, border_color=BORDER,
        )
        if clickable:
            box.configure(cursor="hand2")

        _lbl(box, title, size=10, color=MUTED2).pack(pady=(8, 2))

        img_lbl = ctk.CTkLabel(
            box, text="—", width=PREVIEW_W, height=PREVIEW_H,
            text_color=MUTED, font=ctk.CTkFont(size=11),
        )
        img_lbl.pack(padx=6)

        caption = _lbl(box, "", size=10, color=MUTED2,
                       wraplength=PREVIEW_W, justify="center")
        caption.pack(pady=(2, 10))

        if clickable:
            for w in (box, img_lbl, caption):
                w.bind("<Button-1>", self._browse_png)

        return box, img_lbl, caption

    # ── progress + status ──────────────────────────────────────────────────────

    def _build_bottom(self, parent):
        self._progress = ctk.CTkProgressBar(
            parent, fg_color=SURF2, progress_color=ACCENT,
            height=4, corner_radius=2,
        )
        self._progress.pack(fill="x", pady=(0, 4))
        self._progress.set(0)

        self._status_lbl = _lbl(parent, "Select your save folder to get started.",
                                size=11, color=MUTED)
        self._status_lbl.pack(anchor="w")

    # ══════════════════════════════════════════════════════════════════════════
    # DRAG AND DROP
    # ══════════════════════════════════════════════════════════════════════════

    def _try_enable_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_dnd_drop)
            self._new_img_lbl.configure(text="drop PNG\nor click")
        except Exception:
            self._new_img_lbl.configure(text="click to\nbrowse")

    def _on_dnd_drop(self, event):
        path = event.data.strip().strip("{}").strip('"').strip("'")
        if path.lower().endswith(".png"):
            self._load_png(Path(path))
        else:
            self._set_status("Please drop a PNG file.", error=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FOLDER / SLOT LOGIC
    # ══════════════════════════════════════════════════════════════════════════

    def _browse_save_folder(self):
        p = filedialog.askdirectory(
            title="Select your save folder  (e.g. 0000000000000005)")
        if p:
            self._folder_var.set(p)
            self._on_save_folder_changed()

    def _on_save_folder_changed(self):
        folder_str = self._folder_var.get().strip()
        if not folder_str:
            return
        path = Path(folder_str)
        if not path.is_dir():
            self._set_status("Folder not found.", error=True)
            return

        self._save_dir  = path
        self._slot_dirs = converter.find_slot_dirs(path)

        if not self._slot_dirs:
            self._slot_lbl.configure(text="⚠ no slots found", text_color=ERROR)
            self._set_status(
                "No save slots (0/ or 1/) with a Ugc folder found here.", error=True)
            return

        n = len(self._slot_dirs)
        self._slot_lbl.configure(
            text=f"✓ {n} slot{'s' if n > 1 else ''}", text_color=SUCCESS)
        self._set_status(f"Loaded {n} save slot(s). Select an item.")
        self._refresh_items()

    # ══════════════════════════════════════════════════════════════════════════
    # ITEM LIST
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_items(self):
        if not self._slot_dirs:
            return

        mode = self._mode_var.get().lower()

        # Read names from the first Player.sav we can find
        names: dict[int, str] = {}
        for sd in self._slot_dirs:
            sav = sd / "Player.sav"
            if sav.exists():
                names = converter.get_item_names(sav, mode)
                break

        self._items = converter.get_items(self._slot_dirs[0], mode, names)

        # Clear list
        for w in self._item_scroll.winfo_children():
            w.destroy()
        self._item_rows.clear()
        self._selected = None
        self._clear_editor()

        if not self._items:
            self._item_count_lbl.configure(text="0")
            lbl = _lbl(
                self._item_scroll,
                f"No {mode} items found.\nCreate them in-game first.",
                size=11, color=MUTED, justify="center",
            )
            lbl.pack(pady=24)
            return

        self._item_count_lbl.configure(text=str(len(self._items)))
        for item in self._items:
            self._add_item_row(item)

    def _add_item_row(self, item: converter.ItemInfo):
        row = ctk.CTkFrame(
            self._item_scroll, fg_color=SURF2,
            corner_radius=8, cursor="hand2",
        )
        row.pack(fill="x", pady=(0, 5))

        # Thumbnail area
        thumb_frame = ctk.CTkFrame(
            row, fg_color=SURF, corner_radius=6, width=52, height=52)
        thumb_frame.pack(side="left", padx=(8, 0), pady=8)
        thumb_frame.pack_propagate(False)

        if item.thumb_path:
            try:
                img = converter.decode_thumb(item.thumb_path)
                if img:
                    img.thumbnail((48, 48), Image.LANCZOS)
                    ctk_img = ctk.CTkImage(img, img, (img.width, img.height))
                    self._img_refs.append(ctk_img)
                    lbl_img = ctk.CTkLabel(thumb_frame, image=ctk_img, text="")
                    lbl_img.place(relx=0.5, rely=0.5, anchor="center")
            except Exception:
                pass

        # Name + ID text
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=8)
        _lbl(txt, item.name, size=12, weight="bold", anchor="w").pack(anchor="w")
        _lbl(txt, f"ID {str(item.id).zfill(3)}", size=10,
             color=MUTED2, anchor="w").pack(anchor="w")

        # Click binding on every child widget
        def on_click(e, i=item, r=row):
            self._on_item_selected(i, r)

        for w in self._all_widgets(row):
            try:
                w.bind("<Button-1>", on_click)
            except Exception:
                pass

        self._item_rows[item.id] = row

    @staticmethod
    def _all_widgets(root) -> list:
        """Recursively collect root and all descendant widgets."""
        result = [root]
        for child in root.winfo_children():
            result.extend(App._all_widgets(child))
        return result

    # ══════════════════════════════════════════════════════════════════════════
    # ITEM SELECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _on_item_selected(self, item: converter.ItemInfo,
                          row: Optional[ctk.CTkFrame] = None):
        # Update selection highlight
        for r in self._item_rows.values():
            r.configure(fg_color=SURF2)
        target_row = row if row else self._item_rows.get(item.id)
        if target_row:
            target_row.configure(fg_color=SURF_SEL)

        self._selected = item

        # Show current texture in editor
        self._show_current_texture(item)
        self._item_name_lbl.configure(
            text=f"{item.name}   ·   ID {str(item.id).zfill(3)}",
            text_color=FG,
        )

        # Enable browse; enable replace only if PNG already chosen
        self._browse_btn.configure(state="normal", text_color=FG)
        if self._png_path:
            self._replace_btn.configure(state="normal")

        self._set_status(f"Selected: {item.name}")

    def _show_current_texture(self, item: converter.ItemInfo):
        img: Optional[Image.Image] = None

        # Try full ugctex first, fall back to thumb
        if item.ugctex_path:
            img = converter.decode_ugctex(item.ugctex_path)
        if img is None and item.thumb_path:
            img = converter.decode_thumb(item.thumb_path)

        if img:
            img.thumbnail((PREVIEW_W, PREVIEW_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(img, img, (img.width, img.height))
            self._img_refs.append(ctk_img)
            self._cur_img_lbl.configure(image=ctk_img, text="")
            self._cur_caption.configure(text=item.name, text_color=MUTED2)
        else:
            self._cur_img_lbl.configure(image=None, text="?")
            self._cur_caption.configure(text="—")

    def _clear_editor(self):
        self._cur_img_lbl.configure(image=None, text="—")
        self._cur_caption.configure(text="")
        self._new_img_lbl.configure(image=None, text="click to\nbrowse")
        self._new_caption.configure(text="")
        self._item_name_lbl.configure(
            text="← select an item from the list", text_color=MUTED)
        self._browse_btn.configure(state="disabled", text_color=MUTED2)
        self._replace_btn.configure(state="disabled")

    # ══════════════════════════════════════════════════════════════════════════
    # PNG SELECTION
    # ══════════════════════════════════════════════════════════════════════════

    def _browse_png(self, _event=None):
        if not self._selected:
            self._set_status("Select an item first.", error=True)
            return
        p = filedialog.askopenfilename(
            title="Select PNG Image",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if p:
            self._load_png(Path(p))

    def _load_png(self, path: Path):
        try:
            img = Image.open(path)
            self._png_path = path

            preview = img.copy().convert("RGBA")
            preview.thumbnail((PREVIEW_W, PREVIEW_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(preview, preview, (preview.width, preview.height))
            self._img_refs.append(ctk_img)
            self._new_img_lbl.configure(image=ctk_img, text="")
            self._new_caption.configure(text=path.name, text_color=MUTED2)

            if self._selected:
                self._replace_btn.configure(state="normal")

            self._set_status(f"Loaded: {path.name}")
        except Exception as e:
            self._set_status(f"Could not open image: {e}", error=True)

    # ══════════════════════════════════════════════════════════════════════════
    # CONVERSION
    # ══════════════════════════════════════════════════════════════════════════

    def _on_replace(self):
        if self._converting or not self._selected or not self._png_path:
            return

        self._converting = True
        self._replace_btn.configure(state="disabled", text="Converting…")
        self._progress.set(0)

        item     = self._selected
        png_path = self._png_path
        mode     = self._mode_var.get().lower()
        # Write to Ugc folder inside every slot
        output_dirs = [sd / "Ugc" for sd in self._slot_dirs]
        total       = len(output_dirs)

        def run():
            try:
                results = []
                for idx, out_dir in enumerate(output_dirs):
                    base_pct = idx / total

                    def prog(msg: str, pct: float, b=base_pct):
                        self.after(0, lambda m=msg, p=b + pct / total:
                                   self._on_progress(m, p))

                    cp, up, tp = converter.convert_and_export(
                        png_path=png_path,
                        output_dir=out_dir,
                        item_id=item.id,
                        mode=mode,
                        on_progress=prog,
                    )
                    results.append((cp, up, tp))

                self.after(0, lambda: self._on_success(item.id, total))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, msg: str, pct: float):
        self._progress.set(pct)
        self._set_status(msg)

    def _on_success(self, item_id: int, slot_count: int):
        self._converting = False
        self._replace_btn.configure(state="normal", text="Replace Texture")
        self._progress.set(1.0)
        self._set_status(
            f"Done — written to {slot_count} save slot{'s' if slot_count > 1 else ''} ✓",
            success=True,
        )

        # Refresh list and re-select the same item
        self._refresh_items()
        for it in self._items:
            if it.id == item_id:
                self._on_item_selected(it)
                break

    def _on_error(self, msg: str):
        self._converting = False
        self._replace_btn.configure(state="normal", text="Replace Texture")
        self._progress.set(0)
        self._set_status(f"Error: {msg}", error=True)

    def _set_status(self, msg: str, error=False, success=False):
        color = ERROR if error else (SUCCESS if success else MUTED2)
        self._status_lbl.configure(text=msg, text_color=color)
