# Using the terminal UI

```sh
omamods        # same as `omamods tui`
```

To run `omamods` from any directory while you work on the code, install it as
an editable [uv](https://docs.astral.sh/uv/) tool. Code changes apply at once;
reinstall after changing dependencies in `pyproject.toml` or moving the
checkout to a new path:

```sh
uv tool install --editable .            # puts omamods in ~/.local/bin
uv tool install --editable --reinstall . # after dependency changes
uv tool uninstall omamods
```

The home screen scans for games each time it opens (press `r` to rescan) and
lists them in three groups:

- **Mod-ready**: catalog games OmaMods can install mods for (Cronos, Stellar
  Blade, Cyberpunk 2077, METAL GEAR SOLID Δ, METAL GEAR SOLID V: THE PHANTOM
  PAIN), plus detected Unreal and RE Engine games. Enter opens their mods.
- **In the catalog**: games with a manifest but no installer yet.
- **Your other games**: every other game Steam has installed, in any library
  `libraryfolders.vdf` lists, plus Epic, GOG, Amazon, and sideloaded games
  from Heroic Games Launcher (native or Flatpak). Proton, the Steam Linux
  Runtime, and Steamworks redistributables are hidden.

## Home screen and setup

The detail panel shows the game's folder, library, size, Steam app ID, build,
and Proton prefix. `o` opens the folder in your file manager, `/` filters by
name, and `w` lists records that could not be read. Catalog games match Steam
installs by app ID, never by title. Colors follow Omarchy's current theme, with
OmaMods Night as a fallback; `Ctrl+P` → *Change theme* selects a session palette.

## Add and install a mod

1. Press `K` once and paste your personal Nexus API key
   (nexusmods.com/users/myaccount?tab=api). It is saved to the private config.
2. Press `n` once so the site's **Mod Manager Download** button hands files
   to OmaMods (registers `omamods-nxm.desktop` as the `nxm://` handler with
   `xdg-mime`; it reports the handler it replaced).
3. Pick a game, press `a`, paste a mod page URL, and choose files. Every
   current file is preselected (old and archived versions are not). They
   download into the staging folder,
   `<storage-root>/archives/<game>/<mod-id>/<file-id>/`, next to the mod's
   details (`mod.json`) and main picture.
4. Press `i` to install the mod: all staged MAIN, UPDATE, MISCELLANEOUS, and
   hand-downloaded files at once. OPTIONAL files are left out because they are
   often alternatives. For any archive with several variant folders, a list
   shows them: Space toggles, Enter installs every ticked variant. Variants
   holding the same file names (colours of one outfit, say) are alternatives:
   they start unticked, and ticking one unticks the others. Only the innermost
   folders are variants; paks in a folder above a variant (an outfit's shared
   "Addons", say) install with it. Unreal variants keep their folder path
   under `~mods` (`~mods/hero/armor/black/`). Archives packed inside the
   archive are not installed, and a warning names them.
   Each variant is recorded separately, and uninstalling the file removes all
   of them. Files that would write the same game file are refused with both names, and
   the exact target paths are shown before anything is written.
5. Press Enter on a file to install or uninstall just that file, e.g. to swap
   a main file for an optional one. `u` uninstalls the whole mod, `x` deletes
   the selected download from staging (not if installed), `o` opens
   the picture in `imv`, and `w` opens the mod page.

## Vim keys and commands

The workspace follows your **active Omarchy theme**, including its status and
search colors. Changes apply live, within a second, without restarting OmaMods.
It reads Omarchy's staged `colors.toml` under `~/.local/state/omarchy/current/theme`
(or the legacy config location), without changing desktop configuration. If
Omarchy is absent, the **OmaMods Night** palette is used. A partially written
palette keeps the last valid colors until the update finishes.
Both named colors and Omarchy's generated `color0`–`color15` palettes are
supported. Community theme settings such as terminal opacity and border
gradients are ignored when reading colors.

`Ctrl+p` → **Change theme** selects another palette for the session; the next
Omarchy theme change resumes desktop sync. The bottom statusline shows the
interaction mode, active pane, and cursor position. The key hints follow focus:
files show Enter's exact action, and queues show retry and clear keys.
**Space** opens a searchable action picker: type a name or
description, use `↑`/`↓` (or `Ctrl+j`/`Ctrl+k`) to select, and Enter to run it.
Actions needing an argument open a prefilled `:` line.

Mod files and artwork have independent panes. **p** (or `:preview`) toggles the
artwork; narrow or short terminals hide it automatically to keep the files
visible. The file table adapts too: compact splits show state, filename, and
category; wider splits also show version, size, and file ID. Filenames remain
beside their installed, staged, or available state. The inspector keeps artwork
in proportion and describes the highlighted file's next action. Very wide
terminals center the workspace at a comfortable reading width.

For Unreal games, the inspector's **COLLISIONS** section lists installed mods
that replace the same game assets as the selected mod, or two of its own files
that overlap, for example `overrides Body Tweaks: 8 asset(s) (...);
Outfit_P loads over BodyTweaks_P`. The install confirmation shows the
same warning before anything is written. OmaMods reads each container's
`.utoc` or `.pak` index, not the whole file. Which mod is shown follows
Unreal's load order (see [ADR 5](adr/0005-predict-unreal-asset-load-order.md)):
a `_<n>_P` number wins, then the name that sorts later, so renaming a mod with
a `z_` prefix makes it load last and win. Treat the order as likely, not
certain. Some games change it.

`j`/`k` move, `gg`/`G` jump to the top/bottom, `Ctrl+d`/`Ctrl+u` page, and
`h`/`l` switch panes. `/` filters the games or mods list as you type, like a
LazyVim picker: only names containing every typed word stay, with the words
highlighted, and the panel title shows the filter and its count. Enter keeps the
filter, Esc in the prompt puts back the previous one, and Esc on the list clears
it while staying on the highlighted entry (a second Esc leaves the mods screen).
On the mods screen `n`/`N` cycle through the matches. The `:` and `/` lines sit
on the bottom row like vim's, and `/` shows the live match count there. In the
mods list, `●` marks mods with an installed file and `○` mods that are only
staged.

`:` opens a command line (Tab or the right arrow accepts the suggestion);
commands accept unique prefixes like vim, so `:inst` is `:install`. `:help`
lists the commands for the current screen.

| Command | Does |
| --- | --- |
| `:q`, `:qa` | close this screen, quit OmaMods |
| `:game <name>` | open a game by ID prefix, name, or initials (`:game sb`) |
| `:add <url>` | add a Nexus or AyakaMods mod; opens the URL's game |
| `:install [file]`, `:uninstall [file]` | the whole mod, or one file |
| `:download [file\|all]` | the selected file, one file, or every current file |
| `:rm <file>` | delete a download from staging |
| `:queue`, `:retry`, `:clear` | the download queue |
| `:dl [min\|game\|full]` | size the mods screen's downloads panel |
| `:preview` | toggle the artwork split (`p`) |
| `:stop` | stop waiting for an AyakaMods download |
| `:nsfw [blur\|hide\|show\|mark\|unmark]` | blur, hide, or show NSFW mods, or mark the selected one |
| `:ayaka-login [xf_user]` | save your AyakaMods login (guided without a value) |
| `:key <api-key>`, `:nxm` | setup |

A `file` command argument is the number in the **ID** column or a unique
part of its name. If an old and a current version share a name, the current
one wins.

## NSFW mods

Mods Nexus flags as adult content show a red `18+`. `H` steps through three
modes, which apply to every game and are remembered:

1. **Blur** (default): NSFW mods stay listed, but their picture is heavily
   blurred. `o` still opens the real picture in `imv`.
2. **Hide**: NSFW mods leave the list; the panel's bottom edge counts them.
3. **Show**: NSFW mods and their pictures appear as they are.

`m` marks or unmarks the selected mod as NSFW by hand, for AyakaMods and
hand-staged mods or when Nexus' flag is wrong; a hand mark wins over the flag.
Both are kept in `<storage>/adult_marks.json`. Mods staged before OmaMods read
the flag have none until you add them again (`a` and their URL) or mark them.

## Downloads panel

The mods screen keeps the download queue in a panel along its bottom edge.
`D` grows it in three steps and then shrinks it back:

1. **Minimized** (default): one summary line for every game's downloads, for
   example `↓ Downloads: 1 downloading (ArchiveXL 45% · 1.2 MB/s) · 1 waiting
   for browser · 3 done`. The name in brackets is this game's running download.
2. **This game**: a short table of this game's queue under the mods and
   details.
3. **All games**: the whole queue fills the screen, hiding the mods.

In either table, `r` retries the highlighted download, `x` (or `delete`)
removes it, `c` clears done and failed ones, and `C` clears everything except
downloads still receiving data. Removing a file that is waiting for the
browser also moves that mod's Nexus window on to its next file, or closes it;
`l`/`h` move focus into and out of the table. `:dl full` (or
`min`, `game`) jumps straight to a size. On other screens `D` still opens the
separate queue screen, which `:queue` opens from anywhere.

Premium keys download directly. Without Premium, Nexus only allows downloads
started on its site: the TUI opens the file's page, and your click on **Mod
Manager Download** runs `omamods nxm handle`, which downloads into staging and
sends a desktop notification. The TUI picks the file up within a few seconds.
With a Chromium-family default browser (Brave, Chromium, Vivaldi, ...) on
Hyprland, the page opens in its own app window showing the first file's
download popup. Once your click starts a download, the TUI moves the window
out of sight to Hyprland's hidden `special:omamods` workspace (Hyprland has no
minimise; `hyprctl dispatch togglespecialworkspace omamods` peeks at it). As
each file arrives, the TUI opens the next file's popup in a fresh window, and
closes it once every file you chose has arrived. If a download fails, the
popup comes back so you can click again. To float
and centre that window (and AyakaMods' page window), add Omarchy window rules to
`~/.config/hypr/hyprland.lua`:

```lua
o.window("^brave-www\\.nexusmods\\.com__.*", { float = true, center = true, size = { 1280, 860 } })
o.window("^brave-ayakamods\\.com__.*", { float = true, center = true, size = { 1280, 860 } })
```

Use your browser's class prefix (`chromium-`, `vivaldi-`, ...) instead of
`brave-` if needed. Other browsers get a
normal tab that stays open.
Handler results are logged as JSON lines in `<storage-root>/logs/nxm.jsonl`.
The notification names the file the click actually delivered (name, version,
category) and warns when it is an old version. If a click delivers a file you
did not ask for, the TUI says so and names the file it is still waiting for.

Outside the mods screen, press `D` to open the download queue. It lists every download,
including ones started by browser clicks, with state, progress, speed, time
left, and seconds since data last arrived. A download with no new data for 20
seconds shows as **stalled**. Dropped connections, timeouts, and server errors
(429/5xx) are retried up to five times with growing waits (2-16 s), resuming
where the download stopped; the Error column shows `retrying 2/5 after: ...`.
Expired or refused links (403/404/410) fail at once. Otherwise, `r` retries the selected failed, stalled, or
waiting download, `x` removes it, `c` clears finished entries, and `C`
(`:clear-all`) clears all but active transfers. Each download writes a small
status file to `<storage-root>/downloads/`, which is how the TUI sees
downloads running in the separate browser-handler process.

Pictures render inline in Kitty, Ghostty, and foot; other terminals such as
Alacritty show a coarse block preview, with `o` for full quality.

## AyakaMods

Press `a` (or `:add`) and paste an AyakaMods page URL, such as
`https://ayakamods.com/mods/sample-outfit.7311/`. No API key is
needed: OmaMods reads the name, author, version, picture, and game from the
page, and refuses a mod made for another game. `:add` from any screen opens
the game the page names.

AyakaMods only serves files to a logged-in user and has no mod-manager link
like Nexus' `nxm://`. To download like Nexus, OmaMods needs your login once.
The first time you add or download an AyakaMods mod without one (or once it
expires), OmaMods opens the AyakaMods login page in your browser and a prompt
in the terminal:

1. Log in on ayakamods.com with **Stay logged in** ticked.
2. Open DevTools (`F12`) > **Application** > **Cookies** >
   `https://ayakamods.com` and copy the value of `xf_user` (it looks like
   `347376%2CAbC...`).
3. Back in OmaMods the prompt has already filled it in from the clipboard
   (`wl-paste`; anything not shaped like that cookie is ignored). Press Enter
   and the download starts. Esc downloads through the browser instead.

`:ayaka-login` opens the same prompt any time, and `:ayaka-login <value>` saves
a value directly. The cookie is kept in the private config as
`[ayaka] login_cookie`, like the Nexus key, and is sent only to ayakamods.com,
never to a host a download redirects to.

Then adding a mod (or `d` on one) downloads it straight into staging, with
progress, retries, and resume in the downloads panel. A mod with several files
opens the file picker first. Treat the cookie like a password: it logs in as
you until you log out of AyakaMods in the browser, which also ends it.

Without a saved login, or when it has expired, or when a mod is hosted on
another site (Mega, Drive, ...), OmaMods opens the mod page instead (in its own
app window with a Chromium-family browser, as for Nexus) and watches your
downloads folder (`xdg-user-dir DOWNLOAD`, else `~/Downloads`). Download the
file there as usual. Once the browser has finished writing it, the archive is
moved into staging, the window closes, and `i` installs it like any other
mod. Files already in the folder are ignored, and partial `.crdownload` and
`.part` files are waited out. If your browser asks where to save, pick that
folder.

OmaMods waits for one browser download at a time; adding another mod
replaces the wait, and `:stop` ends it. Anything else that finishes
downloading into the folder while it waits is taken as that mod's file, so
`x` deletes it from staging if it was not. The Nexus requirement check does
not apply to AyakaMods mods.

AyakaMods mods keep their own staging and install records under
`<storage-root>/ayaka/`, because the two sites number their mods
independently.

