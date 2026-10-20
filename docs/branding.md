# OmaMods brand assets

The mark is a game cartridge with a terminal prompt (`>_`) on its label:
game mods, managed from the terminal. The solid label keeps the cartridge
readable at 32 px; at 16 px it reduces to a notched block. It is drawn as
vector paths. The icon uses `#39d98a` for the label, `#29c984` for the pins,
and `#1da773` for the outline, on a `#10231e` square. The preview uses nearby
greens for text and accents.

| Asset | Use |
| --- | --- |
| [`icon.svg`](../icon.svg) | Square app icon and README heading. |
| [`logo.svg`](../logo.svg) | Horizontal wordmark on a dark surface. |
| [`logo-light.svg`](../logo-light.svg) | Horizontal wordmark on a light surface. |
| [`preview.svg`](preview.svg) | Editable README hero layout, with the mark inlined for standalone rendering. |
| [`preview.png`](preview.png) | Rendered README hero at 3840 × 2160. |

The three logo SVGs and the preview inline the mark so they render without
external SVG references. Keep those paths in sync when changing the icon. The
wordmarks use live SVG text rather than outlined glyphs, so their exact font
shape can vary when DejaVu Sans is unavailable.

Keep enough clear space around the mark for its rounded border. Use the
existing colors and wordmark casing, **OmaMods**, when updating screenshots or
project pages. The [preview runbook](runbooks/development.md#refresh-the-preview)
explains how to render the hero from its SVG source and fake TUI captures.
