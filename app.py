from __future__ import annotations

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

import converter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── palette ───────────────────────────────────────────────────────────────────
BG       = "#0b0b10"
SURF     = "#14141f"
SURF2    = "#1c1c2a"
BORDER   = "#26263a"
ACCENT   = "#7c6af6"
ACCENTH  = "#6a58e0"
SUCCESS  = "#34d399"
ERROR    = "#fb7185"
FG       = "#dde0f5"
MUTED    = "#4e4e70"
MUTED2   = "#8282a8"


def _lbl(parent, text, size=12, weight="normal", color=FG, **kw) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, text_color=color,
                        font=ctk.CTkFont(size=size, weight=weight), **kw)


def _row(parent) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color="transparent")


def _card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=SURF, corner_radius=14,
                        border_width=1, border_color=BORDER, **kw)


# ── app ───────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Tomodachi Texture Tool")
        self.geometry("540x590")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        self._png_path: Path | None = None
        self._converting = False

        self._build()
        self._try_enable_dnd()

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self._build_header()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(14, 10))

        self._build_top(body)
        self._build_folder(body)
        self._build_convert(body)

        _lbl(body, "made by farbensplasch", size=10, color=MUTED).pack(
            anchor="e", pady=(6, 0))

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=SURF, corner_radius=0,
                           border_width=0, height=50)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # left accent stripe
        stripe = ctk.CTkFrame(hdr, fg_color=ACCENT, corner_radius=0, width=4)
        stripe.pack(side="left", fill="y")

        _lbl(hdr, "Tomodachi Texture Tool", size=15, weight="bold").pack(
            side="left", padx=16)
        _lbl(hdr, "v1.0", size=11, color=MUTED).pack(side="right", padx=18)

    # ── top two-column section ────────────────────────────────────────────────

    def _build_top(self, parent):
        top = _card(parent)
        top.pack(fill="x", pady=(0, 10))

        top.columnconfigure(0, minsize=190)
        top.columnconfigure(1, weight=1)

        self._build_preview(top)
        self._build_settings(top)

    def _build_preview(self, parent):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="n")

        self._drop_box = ctk.CTkFrame(
            col, width=162, height=162,
            fg_color=SURF2, corner_radius=12, cursor="hand2",
            border_width=1, border_color=BORDER,
        )
        self._drop_box.pack()
        self._drop_box.pack_propagate(False)
        self._drop_box.bind("<Button-1>", self._browse_png)

        self._drop_hint = _lbl(self._drop_box, "click to\nbrowse",
                                size=12, color=MUTED, justify="center")
        self._drop_hint.place(relx=0.5, rely=0.5, anchor="center")
        self._drop_hint.bind("<Button-1>", self._browse_png)

        self._preview_img_lbl = ctk.CTkLabel(self._drop_box, text="")
        self._preview_img_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self._file_info = _lbl(col, "", size=10, color=MUTED2,
                                wraplength=162, justify="center")
        self._file_info.pack(pady=(6, 4))

        ctk.CTkButton(
            col, text="Browse PNG", width=162, height=28,
            fg_color="transparent", border_width=1, border_color=BORDER,
            text_color=MUTED2, hover_color=SURF2,
            font=ctk.CTkFont(size=11),
            command=self._browse_png,
        ).pack()

    def _build_settings(self, parent):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.grid(row=0, column=1, padx=(0, 16), pady=20, sticky="nsew")

        _lbl(col, "Settings", size=13, weight="bold").pack(anchor="w", pady=(0, 14))

        # Item Type
        r = _row(col)
        r.pack(fill="x", pady=(0, 10))
        _lbl(r, "Item Type", size=11, color=MUTED2, width=72, anchor="w").pack(side="left")
        self._mode_var = ctk.StringVar(value="Facepaint")
        ctk.CTkOptionMenu(
            r,
            values=["Facepaint", "Goods", "Clothes", "Exterior",
                    "Interior", "MapObject", "MapFloor", "Food"],
            variable=self._mode_var,
            command=lambda _: self._refresh_highest_id(),
            font=ctk.CTkFont(size=12),
            fg_color=SURF2, button_color=ACCENT, button_hover_color=ACCENTH,
            dropdown_fg_color=SURF2, dropdown_hover_color=ACCENT,
            text_color=FG, dropdown_text_color=FG,
            width=170,
        ).pack(side="left")

        # Divider
        ctk.CTkFrame(col, fg_color=BORDER, height=1).pack(fill="x", pady=(0, 10))

        # Item ID
        r2 = _row(col)
        r2.pack(fill="x")
        _lbl(r2, "Item ID", size=11, color=MUTED2, width=72, anchor="w").pack(side="left")
        self._id_var = ctk.StringVar(value="000")
        ctk.CTkEntry(
            r2, textvariable=self._id_var, width=72,
            placeholder_text="000",
            fg_color=SURF2, border_color=BORDER,
            text_color=FG, placeholder_text_color=MUTED,
            font=ctk.CTkFont(size=13),
        ).pack(side="left")

        self._highest_lbl = _lbl(r2, "", size=11, color=MUTED2)
        self._highest_lbl.pack(side="left", padx=(10, 0))

    # ── ugc folder ────────────────────────────────────────────────────────────

    def _build_folder(self, parent):
        c = _card(parent)
        c.pack(fill="x", pady=(0, 10))
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        r = _row(inner)
        r.pack(fill="x")
        _lbl(r, "Ugc Folder", size=11, color=MUTED2, width=76, anchor="w").pack(side="left")

        self._output_var = ctk.StringVar()
        ctk.CTkEntry(
            r, textvariable=self._output_var,
            placeholder_text="Select your Ugc save folder…",
            fg_color=SURF2, border_color=BORDER,
            text_color=FG, placeholder_text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            r, text="Browse", width=72, height=30,
            fg_color=SURF2, hover_color=BORDER,
            border_width=1, border_color=BORDER,
            text_color=MUTED2, font=ctk.CTkFont(size=11),
            command=self._browse_output,
        ).pack(side="left", padx=(8, 0))

    # ── convert ───────────────────────────────────────────────────────────────

    def _build_convert(self, parent):
        self._convert_btn = ctk.CTkButton(
            parent, text="Convert & Export",
            height=44, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENTH, text_color="#ffffff",
            corner_radius=10,
            command=self._on_convert,
        )
        self._convert_btn.pack(fill="x", pady=(0, 8))

        self._progress = ctk.CTkProgressBar(
            parent, fg_color=SURF2, progress_color=ACCENT,
            height=4, corner_radius=2,
        )
        self._progress.pack(fill="x", pady=(0, 6))
        self._progress.set(0)

        self._status_lbl = _lbl(parent, "Ready", size=11, color=MUTED)
        self._status_lbl.pack(anchor="w")

    # ── drag-and-drop ─────────────────────────────────────────────────────────

    def _try_enable_dnd(self):
        try:
            from tkinterdnd2 import DND_FILES
            self._drop_box.drop_target_register(DND_FILES)
            self._drop_box.dnd_bind("<<Drop>>", self._on_dnd_drop)
            self._drop_hint.configure(text="drop PNG\nor click")
        except Exception:
            pass

    def _on_dnd_drop(self, event):
        path = event.data.strip().strip("{}").strip('"').strip("'")
        if path.lower().endswith(".png"):
            self._load_png(Path(path))
        else:
            self._set_status("Please drop a PNG file.", error=True)

    # ── browsing ──────────────────────────────────────────────────────────────

    def _browse_png(self, _event=None):
        p = filedialog.askopenfilename(
            title="Select PNG Image",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
        )
        if p:
            self._load_png(Path(p))

    def _browse_output(self):
        p = filedialog.askdirectory(title="Select your Ugc save folder")
        if p:
            self._output_var.set(p)
            self._refresh_highest_id()

    # ── image loading ─────────────────────────────────────────────────────────

    def _load_png(self, path: Path):
        try:
            img = Image.open(path)
            self._png_path = path

            thumb = img.copy()
            thumb.thumbnail((152, 152), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=thumb, dark_image=thumb,
                                   size=(thumb.width, thumb.height))
            self._preview_img_lbl.configure(image=ctk_img)
            self._drop_hint.configure(text="")
            self._drop_box.configure(border_color=ACCENT)
            self._file_info.configure(
                text=f"{path.name}\n{img.size[0]}×{img.size[1]}",
                text_color=MUTED2,
            )
            self._set_status(f"Loaded: {path.name}")
        except Exception as e:
            self._set_status(f"Could not open image: {e}", error=True)

    # ── highest ID ────────────────────────────────────────────────────────────

    def _refresh_highest_id(self):
        folder = self._output_var.get().strip()
        path = Path(folder) if folder else None
        if not path or not path.is_dir():
            self._highest_lbl.configure(text="")
            return
        highest = converter.get_highest_id(path, self._mode_var.get().lower())
        if highest is None:
            self._highest_lbl.configure(text="— none found", text_color=MUTED)
        else:
            self._highest_lbl.configure(
                text=f"/ highest: {str(highest).zfill(3)}", text_color=ACCENT)

    # ── conversion ────────────────────────────────────────────────────────────

    def _on_convert(self):
        if self._converting:
            return
        if not self._png_path:
            self._set_status("Select a PNG first.", error=True)
            return
        output_str = self._output_var.get().strip()
        if not output_str:
            self._set_status("Select a Ugc folder first.", error=True)
            return
        try:
            item_id = int(self._id_var.get())
            if not 0 <= item_id <= 999:
                raise ValueError
        except ValueError:
            self._set_status("Item ID must be 0 – 999.", error=True)
            return

        mode = self._mode_var.get().lower()
        self._converting = True
        self._convert_btn.configure(state="disabled", text="Converting…")
        self._progress.set(0)

        def run():
            try:
                cp, up, tp = converter.convert_and_export(
                    png_path=self._png_path,
                    output_dir=Path(output_str),
                    item_id=item_id,
                    mode=mode,
                    on_progress=lambda msg, pct: self.after(
                        0, lambda m=msg, p=pct: self._on_progress(m, p)),
                )
                self.after(0, lambda: self._on_success(cp, up, tp))
            except Exception as exc:
                self.after(0, lambda e=exc: self._on_error(str(e)))

        threading.Thread(target=run, daemon=True).start()

    def _on_progress(self, msg: str, pct: float):
        self._progress.set(pct)
        self._set_status(msg)

    def _on_success(self, cp: Path, up: Path, tp: Path):
        self._converting = False
        self._convert_btn.configure(state="normal", text="Convert & Export")
        self._progress.set(1.0)
        self._set_status(f"Done — wrote {cp.name}, {up.name}, {tp.name}", success=True)
        self._refresh_highest_id()

    def _on_error(self, msg: str):
        self._converting = False
        self._convert_btn.configure(state="normal", text="Convert & Export")
        self._progress.set(0)
        self._set_status(f"Error: {msg}", error=True)

    def _set_status(self, msg: str, error=False, success=False):
        color = ERROR if error else (SUCCESS if success else MUTED2)
        self._status_lbl.configure(text=msg, text_color=color)
