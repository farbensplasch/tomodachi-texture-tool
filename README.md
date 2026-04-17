# TTT (Tomodachi Texture Tool)

A modern GUI tool for converting PNG images into Tomodachi Life: Living the Dream's custom texture formats — no command line required.

---

## Features

- Convert any PNG into game-ready `.canvas.zs` + `.ugctex.zs` files
- Supports all UGC item types: Facepaint, Goods, Clothes, Exterior, Interior, MapObject, MapFloor, Food
- Automatic ZSTD compression
- Shows the highest existing item ID in your save folder
- Drag-and-drop support
- Works on Windows, macOS, and Linux

---

## Download

Head to the [Releases](../../releases/latest) page and download the binary for your platform:

| Platform | File |
|----------|------|
| Windows  | `TomodachiTextureTool-Windows.exe` |
| macOS    | `TomodachiTextureTool-macOS` |
| Linux    | `TomodachiTextureTool-Linux` |

> **macOS / Linux:** you may need to mark the file as executable first:
> ```sh
> chmod +x TomodachiTextureTool-*
> ```

> **macOS Gatekeeper:** right-click → Open the first time if you get a security warning.

---

## How to Use
1. **Backup** your savefolder
2. **Open the tool** and select your PNG image.
3. Set the **Item Type** and **Item ID** matching the file you want to replace.
4. Set the **Ugc Folder** to the `Ugc` directory.
5. Click **Convert & Export** — the tool writes both `.canvas.zs` and `.ugctex.zs` directly to your Ugc folder.
6. (re)launch the game.

---

## File Naming Reference

| Item Type  | Canvas                        | UgcTex                        |
|------------|-------------------------------|-------------------------------|
| Facepaint  | `UgcFacePaintXXX.canvas.zs`  | `UgcFacePaintXXX.ugctex.zs`  |
| Goods      | `UgcGoodsXXX.canvas.zs`      | `UgcGoodsXXX.ugctex.zs`      |
| Clothes    | `UgcClothXXX.canvas.zs`      | `UgcClothXXX.ugctex.zs`      |
| Exterior   | `UgcExteriorXXX.canvas.zs`   | `UgcExteriorXXX.ugctex.zs`   |
| Interior   | `UgcInteriorXXX.canvas.zs`   | `UgcInteriorXXX.ugctex.zs`   |
| MapObject  | `UgcMapObjectXXX.canvas.zs`  | `UgcMapObjectXXX.ugctex.zs`  |
| MapFloor   | `UgcMapFloorXXX.canvas.zs`   | `UgcMapFloorXXX.ugctex.zs`   |
| Food       | `UgcFoodXXX.canvas.zs`       | `UgcFoodXXX.ugctex.zs`       |

`XXX` = zero-padded item ID (e.g. `002`).

---

## Building from Source

**Requirements:** Python 3.11+

```sh
git clone https://github.com/YOUR_USERNAME/tomodachi-texture-tool.git
cd tomodachi-texture-tool
pip install -r requirements.txt
python main.py
```

To build a standalone executable:

```sh
pip install pyinstaller
# Windows
build.bat
# macOS / Linux
bash build.sh
```

---

## Credits

- Nintendo Switch texture swizzle algorithm based on [Aclios/pyswizzle](https://github.com/Aclios/pyswizzle) (MIT)
- File format research by [Timimimi](https://github.com/Timiimiimii/TomoKoreFacepaintTool) and RealDarkCraft
- Made by **farbensplasch**
