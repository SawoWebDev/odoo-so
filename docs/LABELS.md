# Label PDFs: how an item code finds its file

The labels are PDFs that already exist in a shared folder (`\\172.16.0.4\Marketing\00 MASTERLIST\01 PRINTING FILES`).
The app only reads that folder. There is nothing to upload or configure per label.

## Matching

For each order line the item code (Odoo's *Internal Reference*, e.g. `560-BL`) is looked up among **every PDF below the
folder, at any depth**. Case and extra spaces do not matter.

| Item code | File name | Match |
|---|---|---|
| `560-BL` | `560-BL.pdf` | exact |
| `SET-TRAD-D` | `SET-TRAD-D.pdf` | exact |
| `SET-TRAD-D` | `SET-TRAD-D -No BG.pdf`, `SET-TRAD-D (No BG_No Logo).pdf` | **variant**: the code followed by a space, `(` or `_` |
| `460-D` | `460-D2.pdf`, `460-DX.pdf`, `460-D-old.pdf` | **not** a match (no separator) |

Exact files are listed before variants. Only `.pdf` files count (the folder also has a few `.jpg` files, which are ignored).

## One code, several files

About a quarter of the codes exist in more than one place, for example `Individual` and `Box Stickers`, or `Door_Sticker` and
`Door_Sticker/No Logo`. All of them are offered in a dropdown on the order line. The default is, in this order:

1. an exact name over a variant name,
2. the folder preferred by `LABEL_FOLDER_PRIORITY` (e.g. `Box Stickers,Individual`: any path containing the first word wins),
3. the shallower, then shorter, path.

Set `LABEL_FOLDER_PRIORITY` once the team agrees which type is normally printed.

## What the order screen shows for each line

| Line | Look | Can be ticked |
|---|---|---|
| Has a PDF | normal text and its file name | yes |
| Several PDFs | same, with a dropdown | yes |
| **No PDF for the item code** | **warning colour (orange-red), tinted row, "No label PDF"** | no |
| Ordered quantity 0 | grey | no |
| No item code (surcharge, bank charge...) | not listed | n/a |

If the folder itself is unreachable the saved list still matches; the Label files tab shows "cannot be reached" and a print stops with a message.

## The saved list

Adding a folder (Label files tab, admin) reads it **and every sub-folder below it, however deep**, and **saves each PDF's name,
location and URL** (e.g. `file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/P1/.../560-BL.pdf`) in the
database: the folder it belongs to, the path below it, the size, an item code derived from the name, and a status (`ok` or `missing`). Order lines are
matched against this list, and Preview/Print **fetch the file from the saved location**.

| Action | What it does | Changes the list? |
|---|---|---|
| **Add folder** | Reads the folder and saves every PDF | adds files |
| **Read folder** | Reads the folder again | adds new PDFs; marks vanished ones *not found*; restores found-again ones |
| **Rescan** | Scans every saved folder again, all sub-folders | saves new PDFs / images, updates *not found* / *OK* |
| **Delete icon** (red rows only) | Removes the record of a file that is gone | removes that record |
| **Remove** (folder) | Forgets the folder's saved list | removes its records |

Adding a folder that overlaps one already added (a parent or a sub-folder of it) is refused, so no PDF is saved twice.
Nothing here ever changes the share. If a whole folder is unreachable (for example the network is down), Rescan and Read folder
report it and **change nothing**, so an outage cannot turn the list red.

### Renamed or deleted files

A file that is renamed, moved or deleted is simply not at its saved location any more:

* its row on the Label files tab turns **red** ("Not found"), with a 🗑 icon to delete its record;
* an order line that depended on it shows the **warning colour** and cannot be ticked, with the message *"The label file for X was
  deleted or renamed (last saved as ...)"*;
* if the file is renamed and *nobody has rescanned yet*, a Preview or Print that tries to use it stops with a clear message and
  flags the file red on the spot; the line then falls back to another PDF of the same code if there is one;
* a renamed file is a **new** file to the app: *Read folder* saves it under its new name, and the old name stays red until you
  delete that record.

## Printing

* One ticked line = its PDF, repeated *copies* times; several lines are combined in the order ticked.
* The PDF is fetched from its **saved location** at the moment of the preview or print.
* One line with one copy streams the original file untouched (some are very large). Combining is refused above
  `LABEL_MAX_MB` per file, with a message; print such a file on its own.
* Each print is logged with the exact files and a copy of each is kept by SHA-256, so **Reprint** is identical later.

## Folder URLs

`file://172.16.0.4/Marketing/00%20MASTERLIST/01%20PRINTING%20FILES/01%20SAWO/` (also `\\server\share\folder` and
`//server/share/folder`) is mapped to the same folder under `LABEL_MOUNT_DIR` when the server and share match `LABEL_SHARE`.
Anything else is refused with a message: another share, a `file:///C:/...` path on your own PC, a folder that does not exist,
or `..` tricks.

## Connecting Docker to the share

Docker mounts the share itself over SMB, read-only, using a Windows account you provide in `.env`
(`LABEL_SHARE_USER` / `LABEL_SHARE_PASSWORD`; see the README). If the share is reachable but refuses the login, Docker reports
"permission denied" when the backend starts. If the share is unreachable, the *Label files* tab shows "cannot be reached".
