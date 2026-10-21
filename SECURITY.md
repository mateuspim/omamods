# Security

## Reporting a vulnerability

Please report privately through GitHub's
[security advisories](https://github.com/mateuspim/omamods/security/advisories/new)
rather than a public issue. Include the version (`version` in `pyproject.toml`),
your Python version and distribution, steps to reproduce, and impact. You can
expect a reply within a week.

## Supported versions

Only the latest version on `master` receives fixes.

## Privilege model

OmaMods runs unsandboxed as your user, from a terminal. It never asks for root
and never runs `sudo`. This is what it does with your user's access; the
storage layout is in [configuration and storage](docs/configuration.md).

- Reads: Steam libraries (`libraryfolders.vdf`, app manifests, and each user's
  `localconfig.vdf` launch options), Heroic's game records, game folders and
  Proton prefixes (including `msvcp140.dll`'s version), the browser's
  downloads folder while it waits for a file, Omarchy theme files, and the
  clipboard (`wl-paste`) only while the AyakaMods login prompt is open.
  Discovery commands (`omamods game list`, `omamods inspect`) are read-only.
- Writes:
  - Game folders: only files a mod install plans, after a preflight. Installs
    never overwrite a game file (an empty RE Engine placeholder patch is the
    one exception, restored on revert) and record every file they own, so
    revert removes only unchanged owned files.
  - Proton prefixes: a mod's `Engine.ini` for UE4SS bundles; the game's own
    copy is kept in storage and put back on uninstall.
  - Steam `localconfig.vdf`: only when you press `w` in the launch options
    dialog, after a backup, and after asking before it closes a running Steam.
  - Host storage (`~/.local/share/omamods` by default): downloads, install
    records, queue state, caches, backups, and logs.
  - Private config (`~/.config/omamods/config.toml`): created with mode `0600`
    in a `0700` directory and replaced atomically.
  - `nxm://` handler: `omamods nxm register` writes
    `~/.local/share/applications/omamods-nxm.desktop` and sets it as the
    default with `xdg-mime`; startup repairs only an OmaMods entry that points
    at another program.
- Runs: `bsdtar` and `7z` to list and extract archives; `xdg-open`,
  `xdg-settings`, `omarchy-cmd-default-browser`, and a Chromium-family browser
  (`--app`) for mod pages; `hyprctl` to find, hide, and close the windows it
  opened; `wl-copy` and `wl-paste` for the clipboard; `imv` for full-size
  pictures; `notify-send` from the `nxm://` handler; `xdg-mime` and
  `update-desktop-database` to register it; `pgrep` and `steam` to restart
  Steam around a launch-options write.
- Root: never.
- Network (HTTPS only):
  - `api.nexusmods.com` (v1 REST and v2 GraphQL) with your API key, and the
    Nexus download links the API returns, without the key.
  - `ayakamods.com` for mod pages and, with a saved login, file downloads.
    The cookie is sent only to that host; redirects elsewhere drop it.
  - `api.github.com` and `codeberg.org` for release mods, through an
    anonymous transport that never sees your Nexus key or cookie.
- Secrets: the Nexus API key (`[nexus] api_key`, or `NEXUS_API_KEY` for the
  CLI) and the AyakaMods `xf_user` login cookie (`[ayaka] login_cookie`) are
  stored in plain text in the private config above, protected only by file
  permissions. Treat both like passwords, and never commit the config. Each
  is sent only to its own site, as listed under Network.

OmaMods never edits Hyprland or Omarchy configuration.
