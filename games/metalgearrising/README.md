# METAL GEAR RISING: REVENGEANCE adapter

Steam app ID: `235460`. `METAL GEAR RISING REVENGEANCE.exe` is at the top of
the game folder. The game renders 16:9 only: it lists no wider resolution and
pillarboxes everything.

## Ultrawide patch

OmaMods patches the executable itself, so MGROverride and Flawless Widescreen
are not needed. The patch is computed from the untouched Steam build
(SHA-256 `7174741f46ab4c222304b0f1b9291a2281d53368016347e65d2ea404ff07ad34`)
and refuses any other file. Every changed byte is checked against the
original before anything is written.

```sh
omamods patch apply metalgearrising --resolution 3440x1440
omamods patch status metalgearrising
omamods patch revert metalgearrising
```

Then start the game and pick **1920x1080 (16:9)** under Options → Resolution,
in fullscreen. That menu entry now runs at the patched resolution; the label
still says 1920x1080. Any resolution 16:9 or wider works.

What changes:

| Area | Result |
| --- | --- |
| 3D | Fills the whole screen with the correct aspect. |
| Menus | Stay 16:9 and centred, with text aligned. |
| Cutscene movies | Play at 16:9, centred. |
| Gameplay HUD | Still stretched to the full width (a later pass). |
| Menu background movies | Still stretched to the full width. |

`apply` copies the original exe to
`<storage-root>/backups/metalgearrising/` and writes a record to
`<storage-root>/state/metalgearrising/exe-patch.json`. `revert` puts the
original back only while the exe still has the patched hash. If Steam already
restored the original (an update or "Verify integrity of game files"), revert
just clears the record. After a game update that changes the exe, the patch
refuses to apply until it supports the new build.

## How the patch works

Addresses are virtual addresses in the Steam build; the file offset is the
address minus `0x400C00` in `.text` and minus `0x401400` in `.rdata`.

- The 1920x1080 entry's integers (`0xA1D6B2`, `0xA30EAB`) and floats
  (`0x16EBF20`) become the chosen size.
- The camera aspect float at `0x16C3078` becomes width / height.
- The viewport code at `0xF9B975` and `0xF9D537` and the final blit's
  rectangle at `0xA3A836` stop narrowing the picture to 16:9.
- 238 menu-layout calls to the screen width getter (`0xF98A90`), plus the
  cutscene movie width at `0xDFB11C`, call a new getter in int3 padding at
  `0x917FA2` that returns height × 16 / 9. The menu text camera distance
  (loaded at `0xCAD489`) is placed beside it.

The gameplay HUD maps a fixed 1280×720 layout onto the whole frame and is not
fixed yet.
