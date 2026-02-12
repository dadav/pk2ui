"""Main window for PK2 Archive Editor."""

import logging
import time
from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.archive_service import ArchiveOperationCanceled, ArchiveService
from app.version import get_version
from features.comparison.comparison_window import ComparisonWindow
from features.dialogs.open_archive import NewFolderDialog, OpenArchiveDialog
from features.file_details.details_panel import DetailsPanel
from features.text_preview.preview_widget import TextPreviewWidget
from features.tree_browser.filter_panel import FilterPanel
from features.tree_browser.tree_widget import Pk2TreeWidget

logger = logging.getLogger(__name__)


class OpenArchiveWorker(QThread):
    """Worker thread for opening archives without blocking UI."""

    finished = pyqtSignal(bool)  # success status
    progress = pyqtSignal(int, int, float)  # current, total, elapsed_seconds

    def __init__(self, archive_service: "ArchiveService", path: str, key: str) -> None:
        super().__init__()
        self._archive_service = archive_service
        self._path = path
        self._key = key
        self._start_time = 0.0

    def run(self) -> None:
        self._start_time = time.time()

        def on_progress(current: int, total: int) -> None:
            elapsed = time.time() - self._start_time
            self.progress.emit(current, total, elapsed)

        success = self._archive_service.open_archive(
            self._path, self._key, progress=on_progress
        )
        self.finished.emit(success)


class ExtractWorker(QThread):
    """Worker thread for extraction operations with progress reporting."""

    finished = pyqtSignal(bool)  # success status
    progress = pyqtSignal(int, int)  # current, total

    def __init__(
        self,
        archive_service: "ArchiveService",
        pk2_path: str,
        dest_path: str,
        extract_all: bool = False,
    ) -> None:
        super().__init__()
        self._archive_service = archive_service
        self._pk2_path = pk2_path
        self._dest_path = dest_path
        self._extract_all = extract_all
        self._cancel_requested = False
        self._was_canceled = False

    def request_cancel(self) -> None:
        """Request cancellation of the extraction."""
        self._cancel_requested = True

    @property
    def was_canceled(self) -> bool:
        return self._was_canceled

    def run(self) -> None:
        def on_progress(current: int, total: int) -> None:
            self.progress.emit(current, total)

        def is_canceled() -> bool:
            return self._cancel_requested

        try:
            if self._extract_all:
                success = self._archive_service.extract_all(
                    self._dest_path, progress=on_progress, cancel=is_canceled
                )
            else:
                success = self._archive_service.extract_folder(
                    self._pk2_path,
                    self._dest_path,
                    progress=on_progress,
                    cancel=is_canceled,
                )
        except ArchiveOperationCanceled:
            self._was_canceled = True
            success = False

        self.finished.emit(success)


class MultiExtractWorker(QThread):
    """Worker thread for extracting multiple items without blocking UI."""

    finished = pyqtSignal(int, int, bool)  # extracted_count, failed_count, canceled
    progress = pyqtSignal(int, int)  # current, total

    def __init__(
        self,
        archive_service: "ArchiveService",
        items: list[tuple[str, bool]],
        dest_root: str,
    ) -> None:
        super().__init__()
        self._archive_service = archive_service
        self._items = items
        self._dest_root = Path(dest_root)
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Request cancellation of the extraction."""
        self._cancel_requested = True

    def run(self) -> None:
        total = len(self._items)
        extracted = 0
        failed = 0

        def is_canceled() -> bool:
            return self._cancel_requested

        for index, (pk2_path, is_folder) in enumerate(self._items, start=1):
            if is_canceled():
                self.finished.emit(extracted, failed, True)
                return

            try:
                if is_folder:
                    folder_dest = (
                        self._dest_root / pk2_path if pk2_path else self._dest_root / "root"
                    )
                    folder_dest.parent.mkdir(parents=True, exist_ok=True)
                    success = self._archive_service.extract_folder(
                        pk2_path,
                        str(folder_dest),
                        cancel=is_canceled,
                    )
                else:
                    file_dest = self._dest_root / pk2_path
                    file_dest.parent.mkdir(parents=True, exist_ok=True)
                    success = self._archive_service.extract_file(
                        pk2_path,
                        str(file_dest),
                        cancel=is_canceled,
                    )
                if success:
                    extracted += 1
                else:
                    failed += 1
            except ArchiveOperationCanceled:
                self.finished.emit(extracted, failed, True)
                return

            self.progress.emit(index, total)

        self.finished.emit(extracted, failed, False)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PK2 Archive Editor")
        self.setMinimumSize(900, 600)

        # Create service
        self._archive_service = ArchiveService()

        # Setup UI
        self._setup_menu()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()

        # Connect signals
        self._connect_signals()

        # Initial state
        self._update_ui_state()

    def _setup_menu(self) -> None:
        """Setup menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self._open_action = QAction("&Open...", self)
        self._open_action.setShortcut("Ctrl+O")
        self._open_action.triggered.connect(self._on_open)
        file_menu.addAction(self._open_action)

        self._close_action = QAction("&Close", self)
        self._close_action.setShortcut("Ctrl+W")
        self._close_action.triggered.connect(self._on_close)
        file_menu.addAction(self._close_action)

        file_menu.addSeparator()

        self._extract_all_action = QAction("Extract &All...", self)
        self._extract_all_action.triggered.connect(self._on_extract_all)
        file_menu.addAction(self._extract_all_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self._import_action = QAction("&Import File...", self)
        self._import_action.triggered.connect(self._on_import)
        edit_menu.addAction(self._import_action)

        self._import_folder_action = QAction("Import &Folder...", self)
        self._import_folder_action.triggered.connect(self._on_import_folder)
        edit_menu.addAction(self._import_folder_action)

        self._new_folder_action = QAction("&New Folder...", self)
        self._new_folder_action.triggered.connect(self._on_new_folder)
        edit_menu.addAction(self._new_folder_action)

        edit_menu.addSeparator()

        self._delete_action = QAction("&Delete", self)
        self._delete_action.setShortcut("Delete")
        self._delete_action.triggered.connect(self._on_delete)
        edit_menu.addAction(self._delete_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        self._compare_action = QAction("&Compare Archives...", self)
        self._compare_action.triggered.connect(self._on_compare)
        tools_menu.addAction(self._compare_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        """Setup toolbar."""
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._open_btn = QAction("Open", self)
        self._open_btn.triggered.connect(self._on_open)
        toolbar.addAction(self._open_btn)

        self._extract_btn = QAction("Extract", self)
        self._extract_btn.triggered.connect(self._on_extract)
        toolbar.addAction(self._extract_btn)

        self._import_btn = QAction("Import", self)
        self._import_btn.triggered.connect(self._on_import)
        toolbar.addAction(self._import_btn)

        self._new_folder_btn = QAction("New Folder", self)
        self._new_folder_btn.triggered.connect(self._on_new_folder)
        toolbar.addAction(self._new_folder_btn)

    def _setup_central_widget(self) -> None:
        """Setup central widget with splitter layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Filter panel at top (fixed height)
        self._filter_panel = FilterPanel()
        self._filter_panel.setFixedHeight(30)
        layout.addWidget(self._filter_panel)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)  # stretch factor 1 to take remaining space

        # Left: Tree browser
        self._tree_widget = Pk2TreeWidget()
        splitter.addWidget(self._tree_widget)

        # Right: Details + Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Details panel
        self._details_panel = DetailsPanel()
        self._details_panel.setMaximumHeight(150)
        right_layout.addWidget(self._details_panel)

        # Text preview
        self._preview_widget = TextPreviewWidget()
        right_layout.addWidget(self._preview_widget)

        splitter.addWidget(right_widget)

        # Set initial splitter sizes (40% / 60%)
        splitter.setSizes([360, 540])

    def _setup_statusbar(self) -> None:
        """Setup status bar."""
        self._statusbar = self.statusBar()
        self._statusbar.showMessage("Ready")

    def _connect_signals(self) -> None:
        """Connect all signals."""
        # Archive service signals
        self._archive_service.archive_opened.connect(self._on_archive_opened)
        self._archive_service.archive_closed.connect(self._on_archive_closed)
        self._archive_service.archive_modified.connect(self._on_archive_modified)
        self._archive_service.operation_error.connect(self._on_operation_error)

        # Filter panel signals
        self._filter_panel.filters_changed.connect(self._tree_widget.apply_filter)

        # Tree widget signals
        self._tree_widget.file_selected.connect(self._on_file_selected)
        self._tree_widget.folder_selected.connect(self._on_folder_selected)
        self._tree_widget.selection_changed.connect(self._on_selection_changed)
        self._tree_widget.extract_requested.connect(self._on_extract_item)
        self._tree_widget.extract_multiple_requested.connect(self._on_extract_multiple)
        self._tree_widget.delete_requested.connect(self._on_delete_item)
        self._tree_widget.delete_multiple_requested.connect(self._on_delete_multiple)
        self._tree_widget.import_requested.connect(self._on_import_to_folder)
        self._tree_widget.import_folder_requested.connect(self._on_import_folder_to)
        self._tree_widget.new_folder_requested.connect(self._on_new_folder_in)

    def _update_ui_state(self) -> None:
        """Update UI based on current state."""
        is_open = self._archive_service.is_open
        has_selection = self._tree_widget.get_selected_path() is not None

        self._close_action.setEnabled(is_open)
        self._extract_all_action.setEnabled(is_open)
        self._import_action.setEnabled(is_open)
        self._import_folder_action.setEnabled(is_open)
        self._new_folder_action.setEnabled(is_open)
        self._delete_action.setEnabled(is_open and has_selection)

        self._extract_btn.setEnabled(is_open and has_selection)
        self._import_btn.setEnabled(is_open)
        self._new_folder_btn.setEnabled(is_open)

    # Menu/Toolbar actions

    def _on_open(self) -> None:
        """Handle open action."""
        dialog = OpenArchiveDialog(self)
        if dialog.exec():
            path = dialog.file_path
            key = dialog.encryption_key
            if path:
                self._open_archive_async(path, key)

    def _open_archive_async(self, path: str, key: str) -> None:
        """Open archive in background thread with progress dialog."""
        # Use indeterminate progress (0,0) since we can't accurately estimate total blocks
        self._progress = QProgressDialog("Opening archive...", None, 0, 0, self)
        self._progress.setWindowTitle("Opening Archive")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setCancelButton(None)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        self._open_worker = OpenArchiveWorker(self._archive_service, path, key)
        self._open_worker.progress.connect(self._on_open_progress)
        self._open_worker.finished.connect(self._on_open_worker_finished)
        self._open_worker.start()

    def _on_open_progress(self, current: int, total: int, elapsed: float) -> None:
        """Handle archive open progress update."""
        # Show blocks loaded and elapsed time
        if elapsed < 60:
            time_text = f"{elapsed:.1f}s"
        else:
            time_text = f"{elapsed / 60:.1f}m"
        self._progress.setLabelText(f"Opening archive... ({current} blocks, {time_text})")

    def _on_open_worker_finished(self, success: bool) -> None:
        """Handle archive open worker completion."""
        self._progress.close()
        self._open_worker.deleteLater()

    def _on_close(self) -> None:
        """Handle close action."""
        self._archive_service.close_archive()

    def _on_extract_all(self) -> None:
        """Handle extract all action - extract entire archive."""
        dest = QFileDialog.getExistingDirectory(
            self, "Select Destination Folder for Full Extraction", ""
        )
        if dest:
            archive_name = self._archive_service.archive_path.stem if self._archive_service.archive_path else "archive"
            dest_path = str(Path(dest) / archive_name)
            self._start_extraction("", dest_path, extract_all=True)

    def _on_extract(self) -> None:
        """Handle extract action from toolbar."""
        selected_items = self._tree_widget.get_selected_items()
        if len(selected_items) > 1:
            self._on_extract_multiple(selected_items)
        elif len(selected_items) == 1:
            path, is_folder = selected_items[0]
            self._on_extract_item(path, is_folder)

    def _on_import(self) -> None:
        """Handle import action from menu/toolbar."""
        # Import to root or selected folder
        selected = self._tree_widget.get_selected_path()
        if selected and self._tree_widget.get_selected_is_folder():
            self._on_import_to_folder(selected)
        else:
            self._on_import_to_folder("")

    def _on_import_folder(self) -> None:
        """Handle import folder action from menu."""
        selected = self._tree_widget.get_selected_path()
        if selected and self._tree_widget.get_selected_is_folder():
            self._on_import_folder_to(selected)
        else:
            self._on_import_folder_to("")

    def _on_new_folder(self) -> None:
        """Handle new folder action from menu/toolbar."""
        selected = self._tree_widget.get_selected_path()
        if selected and self._tree_widget.get_selected_is_folder():
            self._on_new_folder_in(selected)
        else:
            self._on_new_folder_in("")

    def _on_delete(self) -> None:
        """Handle delete action from menu."""
        selected_items = self._tree_widget.get_selected_items()
        if len(selected_items) > 1:
            self._on_delete_multiple(selected_items)
        elif len(selected_items) == 1:
            path, is_folder = selected_items[0]
            self._on_delete_item(path, is_folder)

    def _on_compare(self) -> None:
        """Open comparison window."""
        self._comparison_window = ComparisonWindow(self)
        self._comparison_window.target_modified.connect(self._on_external_modification)
        self._comparison_window.show()

    def _on_external_modification(self) -> None:
        """Handle external modification to open archive."""
        if self._archive_service.is_open:
            self._archive_service.archive_modified.emit()

    def _on_about(self) -> None:
        """Show about dialog."""
        about_text = (
            f"PK2 Archive Editor v{get_version()}\n\n"
            "A PyQt6 editor for Silkroad Online PK2 archives.\n\n"
            "Uses pk2api library for archive operations."
        )
        if self._archive_service.is_open:
            stats = self._archive_service.get_stats()
            about_text += (
                f"\n\nCurrent archive:\n"
                f"  Files: {stats.get('files', 0):,}\n"
                f"  Folders: {stats.get('folders', 0):,}\n"
                f"  Total size: {self._format_size(stats.get('total_size', 0))}\n"
                f"  Disk used: {self._format_size(stats.get('disk_used', 0))}"
            )
        QMessageBox.about(self, "About PK2 Archive Editor", about_text)

    # Archive service callbacks

    def _on_archive_opened(self, path: str) -> None:
        """Handle archive opened."""
        logger.info("Archive opened: %s", path)
        root = self._archive_service.root_folder
        if root:
            self._tree_widget.populate(root)
        stats = self._archive_service.get_stats()
        size_str = self._format_size(stats.get("total_size", 0))
        self._statusbar.showMessage(
            f"{path} | {stats.get('files', 0)} files, "
            f"{stats.get('folders', 0)} folders | {size_str}"
        )
        self.setWindowTitle(f"PK2 Archive Editor - {Path(path).name}")
        self._update_ui_state()

    def _on_archive_closed(self) -> None:
        """Handle archive closed."""
        logger.info("Archive closed")
        self._tree_widget.clear()
        self._details_panel.clear()
        self._preview_widget.clear_preview()
        self._statusbar.showMessage("Ready")
        self.setWindowTitle("PK2 Archive Editor")
        self._update_ui_state()

    def _on_archive_modified(self) -> None:
        """Handle archive modification - refresh tree."""
        logger.info("Archive modified, refreshing tree")
        root = self._archive_service.root_folder
        if root:
            self._tree_widget.populate(root)
        self._update_ui_state()

    def _on_operation_error(self, title: str, message: str) -> None:
        """Handle operation error."""
        QMessageBox.critical(self, title, message)

    # Tree widget callbacks

    def _on_file_selected(self, file) -> None:
        """Handle file selection."""
        self._details_panel.show_file(file)
        self._preview_widget.preview_file(file)
        self._update_ui_state()

    def _on_folder_selected(self, folder) -> None:
        """Handle folder selection."""
        self._details_panel.show_folder(folder)
        self._preview_widget.clear_preview()
        self._update_ui_state()

    def _on_selection_changed(self, count: int) -> None:
        """Handle selection count change."""
        self._update_ui_state()

    def _on_extract_multiple(self, items: list[tuple[str, bool]]) -> None:
        """Handle extract request for multiple items."""
        dest = QFileDialog.getExistingDirectory(self, "Select Destination Folder", "")
        if not dest:
            return

        self._multi_extract_progress = QProgressDialog(
            "Extracting items...", "Cancel", 0, len(items), self
        )
        self._multi_extract_progress.setWindowTitle("Extracting")
        self._multi_extract_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._multi_extract_progress.setMinimumDuration(0)
        self._multi_extract_progress.setValue(0)
        self._multi_extract_progress.show()

        self._multi_extract_worker = MultiExtractWorker(
            self._archive_service, items, dest
        )
        self._multi_extract_worker.progress.connect(self._on_multi_extract_progress)
        self._multi_extract_worker.finished.connect(self._on_multi_extract_finished)
        self._multi_extract_progress.canceled.connect(
            self._multi_extract_worker.request_cancel
        )
        self._multi_extract_progress.canceled.connect(
            lambda: self._multi_extract_progress.setLabelText("Canceling extraction...")
        )
        self._multi_extract_worker.start()

    def _on_delete_multiple(self, items: list[tuple[str, bool]]) -> None:
        """Handle delete request for multiple items."""
        count = len(items)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete {count} items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Delete in reverse order to handle nested items correctly
        any_deleted = False
        self._archive_service.set_archive_modified_suppressed(True)
        try:
            for pk2_path, is_folder in reversed(items):
                if is_folder:
                    any_deleted = self._archive_service.delete_folder(pk2_path) or any_deleted
                else:
                    any_deleted = self._archive_service.delete_file(pk2_path) or any_deleted
        finally:
            self._archive_service.set_archive_modified_suppressed(False)
            if any_deleted:
                self._archive_service.notify_archive_modified()

    def _on_extract_item(self, pk2_path: str, is_folder: bool) -> None:
        """Handle extract request."""
        if is_folder:
            dest = QFileDialog.getExistingDirectory(
                self, "Select Destination Folder", ""
            )
            if dest:
                folder_name = pk2_path.split("/")[-1] if pk2_path else "root"
                dest_path = str(Path(dest) / folder_name)
                self._start_extraction(pk2_path, dest_path)
        else:
            file_name = pk2_path.split("/")[-1]
            dest, _ = QFileDialog.getSaveFileName(
                self, "Save File As", file_name, "All Files (*)"
            )
            if dest:
                if self._archive_service.extract_file(pk2_path, dest):
                    QMessageBox.information(
                        self, "Extract Complete", f"Extracted to: {dest}"
                    )

    def _start_extraction(
        self, pk2_path: str, dest_path: str, extract_all: bool = False
    ) -> None:
        """Start folder extraction with progress dialog."""
        self._extract_dest = dest_path
        self._extract_progress = QProgressDialog(
            "Extracting files...", "Cancel", 0, 100, self
        )
        self._extract_progress.setWindowTitle("Extracting")
        self._extract_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._extract_progress.setMinimumDuration(0)
        self._extract_progress.setValue(0)
        self._extract_progress.show()

        self._extract_worker = ExtractWorker(
            self._archive_service, pk2_path, dest_path, extract_all
        )
        self._extract_worker.progress.connect(self._on_extract_progress)
        self._extract_worker.finished.connect(self._on_extract_finished)
        self._extract_progress.canceled.connect(self._extract_worker.request_cancel)
        self._extract_progress.canceled.connect(
            lambda: self._extract_progress.setLabelText("Canceling extraction...")
        )
        self._extract_worker.start()

    def _on_extract_progress(self, current: int, total: int) -> None:
        """Handle extraction progress update."""
        if total > 0:
            percent = int(current * 100 / total)
            self._extract_progress.setRange(0, 100)
            self._extract_progress.setValue(percent)
            self._extract_progress.setLabelText(f"Extracting files... ({current}/{total})")
        else:
            self._extract_progress.setRange(0, 0)
            self._extract_progress.setLabelText(f"Extracting files... ({current})")

    def _on_extract_finished(self, success: bool) -> None:
        """Handle extraction completion."""
        self._extract_progress.close()
        self._extract_worker.deleteLater()
        if self._extract_worker.was_canceled:
            QMessageBox.information(self, "Extract Canceled", "Extraction was canceled.")
        elif success:
            QMessageBox.information(
                self, "Extract Complete", f"Extracted to: {self._extract_dest}"
            )

    def _on_multi_extract_progress(self, current: int, total: int) -> None:
        """Handle multi-extract progress update."""
        self._multi_extract_progress.setValue(current)
        self._multi_extract_progress.setLabelText(
            f"Extracting items... ({current}/{total})"
        )

    def _on_multi_extract_finished(
        self, extracted: int, failed: int, canceled: bool
    ) -> None:
        """Handle multi-extract completion."""
        self._multi_extract_progress.close()
        self._multi_extract_worker.deleteLater()
        if canceled:
            QMessageBox.information(
                self, "Extract Canceled", "Extraction was canceled."
            )
        elif failed == 0:
            QMessageBox.information(
                self,
                "Extract Complete",
                f"Extracted {extracted} items.",
            )
        else:
            QMessageBox.warning(
                self,
                "Extract Partial",
                f"Extracted {extracted} items, {failed} failed.",
            )

    def _on_delete_item(self, pk2_path: str, is_folder: bool) -> None:
        """Handle delete request."""
        item_type = "folder" if is_folder else "file"
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete this {item_type}?\n\n{pk2_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if is_folder:
                self._archive_service.delete_folder(pk2_path)
            else:
                self._archive_service.delete_file(pk2_path)

    def _on_import_to_folder(self, target_folder: str) -> None:
        """Handle import request to specific folder."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select File to Import", "", "All Files (*)"
        )
        if file_path:
            file_name = Path(file_path).name
            if target_folder:
                pk2_path = f"{target_folder}/{file_name}"
            else:
                pk2_path = file_name
            self._archive_service.import_file(file_path, pk2_path)

    def _on_import_folder_to(self, target_folder: str) -> None:
        """Handle import folder request to specific folder."""
        folder_path = QFileDialog.getExistingDirectory(
            self, "Select Folder to Import", ""
        )
        if folder_path:
            folder_name = Path(folder_path).name
            if target_folder:
                pk2_path = f"{target_folder}/{folder_name}"
            else:
                pk2_path = folder_name
            imported, failed = self._archive_service.import_folder(folder_path, pk2_path)
            if failed == 0:
                QMessageBox.information(
                    self, "Import Complete", f"Imported {imported} files."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Import Partial",
                    f"Imported {imported} files, {failed} failed.",
                )

    def _on_new_folder_in(self, parent_path: str) -> None:
        """Handle new folder request in specific parent."""
        dialog = NewFolderDialog(parent_path, self)
        if dialog.exec():
            full_path = dialog.full_path
            if full_path:
                self._archive_service.create_folder(full_path)

    def closeEvent(self, event) -> None:
        """Handle window close."""
        self._archive_service.close_archive()
        event.accept()

    def _format_size(self, size: int) -> str:
        """Format byte size for display."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
