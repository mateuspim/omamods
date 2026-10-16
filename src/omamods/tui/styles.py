"""One cohesive terminal workspace, with theme-aware colours and compact splits."""

from textual.theme import Theme

# Tokyo Night inspired palette; Ctrl+P → "Change theme" picks another for the session.
DEFAULT_THEME = "omamods-night"
WORKSPACE_THEME = Theme(
    name=DEFAULT_THEME,
    primary="#bb9af7",
    secondary="#7dcfff",
    accent="#bb9af7",
    foreground="#c0caf5",
    background="#11131e",
    surface="#171a29",
    panel="#21263b",
    success="#9ece6a",
    warning="#e0af68",
    error="#f7768e",
    variables={"text-muted": "#8792b4", "border": "#303850"},
)

APP_CSS = """
Screen { background: $background; }
WorkspaceScreen { align-horizontal: center; }
.workspace-header, .workspace-status, .workspace-hints { max-width: 220; }
.workspace-header {
    height: 2; padding: 0 2; align: left middle;
    background: $background; border-bottom: solid $panel;
}
.workspace-header Static { height: 1; }
.workspace-brand { width: 16; color: $primary; text-style: bold; }
.workspace-context { width: 1fr; color: $text; text-style: bold; }
.workspace-badge { width: auto; color: $text-muted; }
.workspace-status { height: 1; background: $panel; }
.workspace-status Static { height: 1; }
.workspace-mode {
    width: 11; content-align: center middle; text-style: bold;
    background: $secondary; color: $background;
}
.workspace-mode.editing { background: $primary; }
.workspace-path { width: 1fr; padding: 0 2; color: $text; }
.workspace-position { width: auto; padding: 0 2; color: $secondary; }
.workspace-hints { height: 1; padding: 0 2; color: $text-muted; }
.workspace-hints Static { height: 1; }
.hints-context { width: 1fr; }
.hints-global { width: auto; padding-left: 2; color: $secondary; }

/* Panels share a restrained frame; focus lights up the active split. */
#games, #mods, #game-card, #detail, #preview-pane, #queue {
    border: solid $panel; border-title-color: $text-muted;
    border-title-style: bold; background: $surface;
}
#games:focus, #mods:focus, #queue:focus, #detail:focus-within {
    border: solid $primary; border-title-color: $primary;
}
#home, #mods-body { height: 1fr; margin: 0 1; max-width: 220; }
#games { width: 43%; min-width: 28; max-width: 60; height: 1fr; padding: 0 1; }
#games > .option-list--option, #mods > .option-list--option { padding: 0 1; }
#games > .option-list--option-highlighted,
#mods > .option-list--option-highlighted {
    background: $primary 12%; text-style: none; color: $text;
}
#games:focus > .option-list--option-highlighted,
#mods:focus > .option-list--option-highlighted {
    background: $primary 25%; color: $text;
}
#games > .option-list--option-disabled,
#mods > .option-list--option-disabled { color: $secondary; padding-top: 1; }
#game-card { width: 1fr; padding: 1 3; margin-left: 1; }
.pane-eyebrow { height: 2; color: $secondary; text-style: bold; }
#setup { height: 2; padding: 0 2; content-align: left middle; color: $text-muted; }

/* 1fr: an auto-height list left an unstyled gap under a short or filtered list. */
#mods { width: 20%; min-width: 26; max-width: 42; height: 1fr; padding: 0; }
ModDetail { width: 1fr; height: 1fr; }
#detail { width: 1fr; min-width: 24; padding: 0 1; margin-left: 1; }
#details { height: auto; max-height: 7; padding: 1 1; color: $text; }
#files { height: 1fr; margin-top: 1; }
DataTable { background: $surface; }
DataTable > .datatable--header { background: $panel; color: $secondary; text-style: bold; }
DataTable > .datatable--odd-row { background: $surface; }
DataTable > .datatable--even-row { background: $primary 4%; }
DataTable > .datatable--cursor { background: $primary 18%; color: $text; }
DataTable:focus > .datatable--cursor { background: $primary 30%; color: $text; }
#preview-pane { width: 34%; max-width: 56; min-width: 28; padding: 1; margin-left: 1; }
#picture { height: auto; min-height: 5; max-height: 45%; align: center top; overflow: hidden hidden; }
/* Both auto dimensions let textual-image contain artwork at its original ratio. */
#picture Image { width: auto; height: auto; max-width: 100%; max-height: 100%; }
.preview-caption { height: 2; color: $text-muted; content-align: center middle; }
.inspector-label {
    border-top: solid $panel; height: 3; margin-top: 1;
    padding-top: 1; color: $secondary; text-style: bold;
}
#mod-overview, #file-inspector { height: auto; padding: 0 1; }
.nsfw-note { dock: top; color: $error; text-style: bold; height: 2; }
#status { display: none; }
.placeholder { color: $text-muted; content-align: center middle; height: 100%; }

#queue { height: 1fr; margin: 1; max-width: 220; }
#queue-help { height: 2; color: $text-muted; padding: 0 2; }
#downloads-panel {
    border-top: solid $panel; border-title-color: $secondary;
    border-title-style: bold; background: $background;
    padding: 0 1; margin: 0 1; height: auto;
    max-width: 220;
}
#downloads-panel:focus-within { border-top: solid $primary; }
#downloads-panel.minimized #downloads-table { display: none; }
#downloads-panel.game { height: 9; max-height: 40%; }
#downloads-panel.full { height: 1fr; }
#downloads-table { height: 1fr; }
#downloads-bar { height: 1; color: $text-muted; }
.downloads-full #mods-body { display: none; }

/* Like vim, the : and / lines leave the list fully visible behind them. */
.command-screen { align: left bottom; background: transparent; }
/* One row over the footer, like vim's command line, instead of a bordered box. */
#command-bar { dock: bottom; height: 1; background: $panel; }
#command-prefix { width: auto; padding: 0 1; color: $secondary; text-style: bold; }
#command-line, #command-line:focus {
    width: 1fr; height: 1; border: none; padding: 0; background: $panel;
}
#command-hint { width: auto; padding: 0 1; color: $text-muted; }
#command-hint.no-matches { color: $error; }
ModalScreen { align: center middle; background: $background 75%; }
.dialog {
    width: 70; max-width: 94%; height: auto; max-height: 90%; padding: 1 2;
    border: round $primary; background: $surface;
}
.dialog.wide { width: 100; max-height: 90%; }
.dialog.large { width: 90%; max-width: 180; max-height: 90%; }
#requirement-body { height: auto; max-height: 70vh; }
#requirement-body .notes { margin-top: 1; }
.dialog-title { text-style: bold; color: $primary; margin-bottom: 1; }
.hint { color: $text-muted; margin-top: 1; }
Input { border: tall $panel; background: $background; }
Input:focus { border: tall $primary; }
SelectionList { border: none; background: $background; }
SelectionList:focus { border: none; }
#action-picker {
    width: 88; max-width: 94%; height: auto; max-height: 85%;
    padding: 1 2; border: round $primary; background: $surface;
}
#action-results { height: auto; max-height: 14; border: none; background: $surface; }
#action-results > .option-list--option-highlighted { background: $primary 22%; }
#action-results > .option-list--option { padding: 0 1; }

.compact-width .workspace-badge { display: none; }
.compact-width #mods { width: 26; }
.compact-width #preview-pane { display: none; }
.compact-width #game-card { padding: 1; }
.compact-width .workspace-position { padding: 0 1; }
.compact-width .hints-global { padding-left: 1; }
.compact-height #home, .compact-height #mods-body { margin-top: 0; }
.compact-height #preview-pane { display: none; }
.compact-height #details { max-height: 4; padding: 0 1; }
.compact-height #files { margin-top: 0; }
.compact-height #setup { height: 1; }
.compact-height .workspace-header { height: 2; }
.compact-height .pane-eyebrow { height: 1; }
.preview-requested #preview-pane { display: block; }
.compact-width.preview-requested #preview-pane { min-width: 20; width: 32%; }
.preview-hidden #preview-pane { display: none; }
"""
