"""The TUI's look: one stylesheet and the default colour theme."""

# Omarchy's default palette; Ctrl+P → "Change theme" picks another for the session.
DEFAULT_THEME = "tokyo-night"

APP_CSS = """
Screen { background: $background; }
Header { background: $panel; color: $accent; text-style: bold; }
Footer { background: $panel; }

/* Panels share one rounded frame that lights up when focused. */
#games, #mods, #game-card, #detail, #setup {
    border: round $panel-lighten-2;
    border-title-color: $text-muted;
    border-title-style: bold;
    background: $surface;
}
#games:focus, #mods:focus, #queue:focus {
    border: round $accent;
    border-title-color: $accent;
}

#home { height: 1fr; }
#games { width: 44%; min-width: 36; height: 1fr; padding: 0 1; }
#games > .option-list--option-highlighted { background: $accent 25%; text-style: none; }
#games:focus > .option-list--option-highlighted { background: $accent 40%; }
#games > .option-list--option-disabled { color: $secondary; }
#game-card { width: 1fr; padding: 1 2; }
#setup { height: 3; padding: 0 1; }

#queue { height: 1fr; border: round $panel-lighten-2; }
#queue-help { color: $text-muted; padding: 0 1; }
#mods { width: 34; }
#detail { padding: 0 1; }
#picture { height: 20; }
#picture Image { width: auto; height: 100%; }
#details { margin: 1 0; }
#files { height: auto; max-height: 14; }
#status { color: $text-muted; padding: 0 1; }
#command-line { dock: bottom; border: tall $accent; }
.command-screen { align: left bottom; }
.placeholder { color: $text-muted; content-align: center middle; height: 100%; }
.dialog {
    width: 70; height: auto; padding: 1 2;
    border: round $accent; background: $surface;
}
.dialog.wide { width: 100; max-height: 90%; }
.dialog.large { width: 90%; max-width: 180; max-height: 90%; }
#requirement-body { height: auto; max-height: 70vh; }
#requirement-body .notes { margin-top: 1; }
.dialog-title { text-style: bold; color: $accent; margin-bottom: 1; }
.hint { color: $text-muted; margin-top: 1; }
ModalScreen { align: center middle; background: $background 60%; }
"""
