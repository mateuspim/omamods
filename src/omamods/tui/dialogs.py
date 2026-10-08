"""Small modal dialogs shared by the TUI screens."""

from collections.abc import Mapping

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, SelectionList, Static

from omamods.mod_plan import preselected_download
from omamods.nexus_api import NexusFile


class TextPrompt(ModalScreen[str | None]):
    """Ask for one line, e.g. a mod URL or an API key."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, placeholder: str, secret: bool = False) -> None:
        super().__init__()
        self.title_text = title
        self.placeholder = placeholder
        self.secret = secret

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            yield Input(placeholder=self.placeholder, password=self.secret)
            yield Static("Enter to confirm, Esc to cancel", classes="hint")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


def file_label(file: NexusFile) -> str:
    """Describe a file in lists; for example, ``file_label(file)``."""
    name = file.display_name or file.file_name
    size = f"{file.size_kb / 1024:.1f} MB" if file.size_kb else "size unknown"
    version = f" v{file.version}" if file.version else ""
    return f"[{file.category}] {name}{version} - {size}"


class FilePicker(ModalScreen[tuple[NexusFile, ...] | None]):
    """Choose which of a mod's files to download into staging."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Download selected", priority=True),
    ]

    def __init__(self, title: str, files: tuple[NexusFile, ...]) -> None:
        super().__init__()
        self.title_text = title
        self.files = files

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            yield SelectionList[int](
                *(
                    (file_label(f), f.file_id, preselected_download(f))
                    for f in self.files
                )
            )
            yield Static(
                "Space toggles, Enter downloads selected, Esc cancels", classes="hint"
            )

    def action_confirm(self) -> None:
        chosen = set(self.query_one(SelectionList).selected)
        self.dismiss(tuple(f for f in self.files if f.file_id in chosen))

    def action_cancel(self) -> None:
        self.dismiss(None)


class VariantPicker(ModalScreen[tuple[str, ...] | None]):
    """Choose which variant folders of an archive to install.

    Variants start ticked unless they exclude others; ticking one of those
    unticks the variants it excludes, so at most one of them installs.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Install selected", priority=True),
    ]

    def __init__(
        self,
        title: str,
        variants: tuple[str, ...],
        exclusive: Mapping[str, frozenset[str]] | None = None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.variants = variants
        self.exclusive = exclusive or {}

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self.title_text, classes="dialog-title")
            yield SelectionList[str](
                *((v, v, not self.exclusive.get(v)) for v in self.variants)
            )
            hint = "Space toggles, Enter installs selected, Esc cancels"
            if any(self.exclusive.values()):
                hint += "\nVariants with the same files are alternatives: pick one"
            yield Static(hint, classes="hint")

    def on_selection_list_selection_toggled(
        self, event: SelectionList.SelectionToggled[str]
    ) -> None:
        picker = self.query_one(SelectionList)
        ticked = event.selection.value
        if ticked not in picker.selected:
            return
        for other in self.exclusive.get(ticked, frozenset()):
            picker.deselect(other)

    def action_confirm(self) -> None:
        chosen = set(self.query_one(SelectionList).selected)
        picked = tuple(v for v in self.variants if v in chosen)
        self.dismiss(picked or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmDialog(ModalScreen[bool]):
    """Show what will change and ask before writing to the game folder."""

    BINDINGS = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n,escape", "answer(False)", "No"),
    ]

    def __init__(self, title: str, details: str) -> None:
        super().__init__()
        self.title_text = title
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(self.details, markup=False)
            yield Static("y to confirm, n to cancel", classes="hint")

    def action_answer(self, accepted: bool) -> None:
        self.dismiss(accepted)


class InfoDialog(ModalScreen[None]):
    """Show read-only text such as ':help'; any of Esc, q, or Enter closes it."""

    BINDINGS = [Binding("escape,q,enter", "close", "Close")]

    def __init__(self, title: str, details: str) -> None:
        super().__init__()
        self.title_text = title
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(self.details, markup=False)
            yield Static("Esc, q, or Enter closes", classes="hint")

    def action_close(self) -> None:
        self.dismiss(None)
