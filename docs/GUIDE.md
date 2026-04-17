# How to Use — Tomodachi Texture Tool

This guide walks you through replacing the texture of a custom item (like a Treasure/Good) with your own image. The process is the same for all item types.

---

## Part 1 — Create a placeholder item in-game

You need to create the item in-game first so the game generates the save files for it.

**1.** Launch Tomodachi Life.

![](images/02_game_icon.png)

**2.** Go to the **Werkstatt** (Workshop) building on your island.

![](images/06_workshop.png)

**3.** Select **Neue Kreation** (New Creation).

![](images/07_new_creation.png)

**4.** Pick the category matching what you want to create. In this example we pick **Schätze** (Treasures / Goods).

![](images/08_category.png)

**5.** Choose **Frei gestalten** (Free design) — draw anything as a placeholder, it doesn't matter what.

![](images/09_free_design.png)

![](images/10_draw.png)

**6.** Give it a name and finish the setup screens (gender, properties, etc.), then confirm.

![](images/11_name.png)

![](images/12_properties.png)

**7.** You'll see the finished item. Now click **Beenden** (Quit) to save and exit the workshop.

![](images/13_item_done.png)

**8.** Save the game and close it.

---

## Part 2 — Find your Ugc save folder

**9.** In Ryujinx, right-click Tomodachi Life and select **Open User Save Directory**.

![](images/03_open_save_dir.png)

**10.** A folder will open. Navigate into the **Ugc** subfolder — this is where the game stores all custom item files.

![](images/01_save_folder.png)

Copy the full path to the **Ugc** folder, you'll need it in the next step.

---

## Part 3 — Convert your image with the tool

**11.** Open **TomodachiTextureTool.exe**.

![](images/04_tool_exe.png)

![](images/05_tool_empty.png)

**12.** Click **Browse** next to **Ugc Folder** and select the Ugc folder from the previous step.

![](images/14_ugc_folder.png)

**13.** Set the **Item Type** to match what you created in-game (e.g. **Goods** for Treasures). The tool will show you the **highest** existing ID in your folder — this is the item you just created.

![](images/15_highest_id.png)

**14.** Set the **Item ID** to the highest number shown.

**15.** Click the image box or **Browse PNG** and select your image file.

![](images/16_browse_png.png)

**16.** Your image will appear as a preview. Double-check the Item Type and Item ID are correct.

![](images/17_tool_ready.png)

**17.** Click **Convert & Export**. When it's done you'll see a green confirmation message with the two filenames that were written.

![](images/18_tool_done.png)

---

## Part 4 — Apply the texture in-game

**18.** Launch Tomodachi Life again.

**19.** Go to **Werkstatt → Kreationen** (Creations).

![](images/19_kreationen.png)

**20.** Find your item in the list and select it.

![](images/20_item_list.png)

**21.** Click **Design ändern** (Change design).

![](images/21_design_change.png)

**22.** You'll see your custom image loaded in the drawing editor. Press **Fertig** (Done / +) to confirm without changing anything.

![](images/22_editor_result.png)

**23.** Your item now has the custom texture applied and is visible in-game!

![](images/23_final_result.png)

---

## Notes

- The image will be resized to fit while keeping its aspect ratio.
- Transparency works, but only fully transparent or fully opaque pixels — partial transparency (e.g. 50% opacity) will look wrong.
- The same process works for every item type (Clothes, Exterior, Food, etc.) — just select the matching Item Type in the tool.
