"""File selection and creation widgets."""

from collections.abc import Iterable
import pathlib
from typing import cast, Optional

import textual
from textual import app, containers, message, widgets


class FileSelectorTree(widgets.DirectoryTree):
    """Custom widget for selecting and creating files."""

    class ItemSelected(message.Message):
        """Sent when a database file is selected."""

        path: pathlib.Path

        def __init__(self, path) -> None:
            """Set the filesystem path."""
            super().__init__()
            self.path = path

    filetypes: Optional[list[str]]
    """Filter directory tree to show only files with these suffixes.
    
    Include the period when specifying suffixes, e.g., [".db", ".sqlite3"]
    """

    def __init__(self, path: pathlib.Path, filetypes: Optional[list[str]]) -> None:
        """Initialize with default DB file name."""
        super().__init__(path)
        self.filetypes = filetypes

    def filter_paths(self, paths: Iterable[pathlib.Path]) -> Iterable[pathlib.Path]:
        """Only show files with specified suffixes."""
        if self.filetypes is None:
            return paths
        return [
            path for path in paths if path.is_dir() or path.suffix in self.filetypes
        ]

    def on_directory_tree_file_selected(
        self, event: widgets.DirectoryTree.FileSelected
    ) -> None:
        """Notify parent of file selection."""
        self.post_message(self.ItemSelected(event.path))

    def on_directory_tree_directory_selected(
        self, event: widgets.DirectoryTree.DirectorySelected
    ) -> None:
        """Navigate tree to selected folder.."""
        self.path = event.path


class FileSelector(containers.Horizontal):
    """Select or create a new file."""

    class FileSelected(message.Message):
        """Message sent when file selected or on file creation."""

        path: pathlib.Path
        create: bool
        id: Optional[str]

        def __init__(
            self, path: pathlib.Path, create: bool = False, id: Optional[str] = None
        ) -> None:
            super().__init__()
            self.path = path
            self.create = create
            self.id = id

    create: bool
    """Set to True to create a new file. Can only select files when False."""
    default_filename: Optional[str]
    """Initial value for filename input widget."""
    filetypes: Optional[list[str]]
    """Filter directory tree to show only files with these suffixes."""
    start_path: pathlib.Path
    """Initial file system path for directory tree."""

    def __init__(
        self,
        start_path: pathlib.Path,
        filetypes: Optional[list[str]],
        create: bool = False,
        default_filename: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ) -> None:
        """Set create or select mode on initialization."""
        super().__init__(id=id, classes=classes)
        self.start_path = start_path
        self.create = create
        self.default_filename = default_filename
        self.filetypes = filetypes

    def compose(self) -> app.ComposeResult:
        """Add widgets to screen."""
        with containers.VerticalGroup(id="file-widget-controls"):
            yield widgets.Button(
                "Home", id="to-start-path", tooltip="Go back to the initial folder."
            )
            yield widgets.Button(
                "Up ..",
                id="to-parent-folder",
                tooltip="Navigate up to the parent folder.",
            )
            if self.create:
                yield widgets.Label("Filename:", classes="emphasis")
                yield widgets.Input(self.default_filename, id="filename")
                yield widgets.Button("Create File", id="create-file", classes="ok")
                yield widgets.Static(
                    "Click on [i]Create File[/] to create a file with the "
                    "specified filename in the folder displayed in the directory tree, "
                    "or select [i]Cancel[/] to take no action."
                )
            else:
                yield widgets.Static(
                    "Select a file in the directory tree at right to open it, "
                    "or select [i]Cancel[/] to take no action."
                )
            yield widgets.Button(
                "Cancel",
                id="cancel-action",
                classes="cancel",
                tooltip="Close the file selector and take no action.",
            )
        yield FileSelectorTree(self.start_path, self.filetypes)

    @textual.on(widgets.Button.Pressed, "#to-start-path")
    def return_to_start_path(self) -> None:
        """Return to initial path shown in directory tree."""
        self.query_one(FileSelectorTree).path = self.start_path

    @textual.on(widgets.Button.Pressed, "#to-parent-folder")
    def navigate_to_parent_folder(self) -> None:
        selector_tree = self.query_one(FileSelectorTree)
        selector_tree.path = cast(pathlib.Path, selector_tree.path).parent

    def on_file_selector_tree_item_selected(
        self, message: FileSelectorTree.ItemSelected
    ) -> None:
        """Respond to file selection in directory tree."""
        # Ignore item selections in create mode.
        if self.create:
            return
        self.post_message(self.FileSelected(message.path, create=False, id=self.id))
        self.remove()

    @textual.on(widgets.Button.Pressed, "#create-file")
    def create_file(self) -> None:
        """Send message to create a file."""
        # TODO: Add error handling.
        selector_tree = self.query_one(FileSelectorTree)
        file_name = self.query_one("#filename", widgets.Input).value
        if file_name == "" or file_name is None:
            return
        directory = cast(pathlib.Path, selector_tree.path)
        full_path = directory / file_name
        if full_path.exists():
            return
        self.post_message(self.FileSelected(full_path, create=True, id=self.id))
        self.remove()

    @textual.on(widgets.Button.Pressed, "#cancel-action")
    def remove_selector(self) -> None:
        """Remove the database selector widgets on cancel."""
        self.remove()
