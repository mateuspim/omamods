"""The confirm dialog for "install a mod with its requirements".

Requirement plans list long Nexus file names, so this dialog takes most of
the screen, shows a table, and scrolls instead of cutting the plan off.
"""

from rich.table import Table
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from omamods.tui.launch_options_dialog import (
    TextCopier,
    copy_launch_line,
    launch_options_lines,
)
from omamods.requirement_chain import ChainStep
from omamods.tui.requirement_flow import RequirementPlan


def file_size(size_kb: int) -> str:
    """Show a Nexus size; e.g. ``file_size(40) == '40 KB'``."""
    if not size_kb:
        return ""
    return f"{size_kb} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"


def _file_cells(step: ChainStep) -> tuple[str, str, str]:
    files = step.files
    names = "\n".join(f.display_name or f.file_name for f in files)
    versions = "\n".join(f.version for f in files)
    sizes = "\n".join(file_size(f.size_kb) for f in files)
    return names, versions, sizes


def requirement_table(plan: RequirementPlan) -> Table:
    """Number each install; e.g. ``Static(requirement_table(plan))``."""
    table = Table(expand=True, show_edge=False, header_style="bold")
    table.add_column("#", justify="right", width=3)
    table.add_column("Mod", ratio=2)
    table.add_column("File", ratio=3, overflow="fold")
    table.add_column("Version", no_wrap=True)
    table.add_column("Size", justify="right", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    for index, step in enumerate(plan.steps, 1):
        table.add_row(str(index), step.name, *_file_cells(step), _status(plan, step))
    last = str(len(plan.steps) + 1)
    name = f"{plan.target.name} (this mod)"
    table.add_row(last, name, *_file_cells(plan.target), _status(plan, plan.target))
    return table


def _status(plan: RequirementPlan, step: ChainStep) -> Text:
    if step.mod_id in plan.staged:
        return Text("downloaded", style="green")
    return Text("to download", style="yellow")


def requirement_notes(plan: RequirementPlan) -> str:
    """Explain what OmaMods leaves to you; e.g. ``requirement_notes(plan)``."""
    tree = plan.tree
    notes = [
        ("Already installed", plan.present),
        ("No MAIN file to pick, install by hand", plan.unresolved),
        ("Needs DLC (not checked)", tree.dlc),
        ("Off-site, install by hand", tree.external),
    ]
    lines = [f"{label}: {', '.join(names)}." for label, names in notes if names]
    advice = plan.launch_advice
    if advice is not None and advice.needed:
        lines.append("⚠ " + launch_options_lines(advice).replace("\n\n", "\n"))
    lines.append(
        "Files download one at a time; without Premium, click 'Mod Manager "
        "Download' as each Nexus window opens. Each installs when it arrives."
    )
    return "\n".join(lines)


class RequirementsDialog(ModalScreen[bool]):
    """Ask before installing a requirement chain; e.g. ``RequirementsDialog(plan)``."""

    BINDINGS = [
        Binding("y", "answer(True)", "Yes"),
        Binding("n,escape", "answer(False)", "No"),
        Binding("c", "copy_launch_line", "Copy launch options"),
    ]

    def __init__(self, plan: RequirementPlan, copier: TextCopier) -> None:
        super().__init__()
        self.plan = plan
        self.copier = copier

    def compose(self) -> ComposeResult:
        count = len(self.plan.steps) + len(self.plan.unresolved)
        title = f"{self.plan.target.name} needs {count} more mod(s); install in order?"
        with Vertical(classes="dialog large"):
            yield Label(title, classes="dialog-title")
            with VerticalScroll(id="requirement-body"):
                yield Static(requirement_table(self.plan))
                yield Static(
                    requirement_notes(self.plan), classes="notes", markup=False
                )
            copy = ", c copies the launch options" if self.plan.missing_dlls else ""
            yield Static(f"y installs all, n cancels{copy}, j/k scroll", classes="hint")

    def action_copy_launch_line(self) -> None:
        if self.plan.launch_advice is not None:
            copy_launch_line(self, self.plan.launch_advice, self.copier)

    def action_answer(self, accepted: bool) -> None:
        self.dismiss(accepted)
