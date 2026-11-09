# 8. Patch game executables from verified bytes

- Status: Accepted
- Documented: 2026-11-08

## Context

Some games need code changes no archive provides. METAL GEAR RISING:
REVENGEANCE renders 16:9 only, and the known fixes are a Windows patcher
(MGROverride) plus a closed-source trainer (Flawless Widescreen). Both edit
the executable or its memory. OmaMods installs files it can track, and an exe
is a file the game owns, so replacing it needs its own rules.

## Decision

Treat an executable patch as a built-in mod computed from the game's own file.
Each patch is a list of byte replacements, and each names the bytes it expects.
The whole patch is refused if the exe's SHA-256 is not the build it was made
for, or if any expected byte differs. Before the exe is replaced, the original
is copied to `<storage-root>/backups/<game>/`, and a record with the original
and patched hashes goes to `<storage-root>/state/<game>/exe-patch.json`. The
exe is written through a temporary file and an atomic rename. Revert restores
the copy only while the exe still has the patched hash. If the exe already has
the original hash, revert only clears the record. Any other hash stops revert
and points to Steam's file verification. Manifests mark these games with the
`exe-patcher` adapter.

## Consequences

- A game update that changes the exe disables the patch until a new build is
  supported, instead of corrupting the new exe.
- Values that depend on the user, such as the resolution, are computed when
  applying. Changing them means revert, then apply again.
- The backup doubles the exe's disk use in storage while the patch is applied.

See `src/omamods/exe_byte_patches.py`, `src/omamods/exe_patch_install.py`,
`src/omamods/mgr_ultrawide.py`, and the
[METAL GEAR RISING adapter](../../games/metalgearrising/README.md).
