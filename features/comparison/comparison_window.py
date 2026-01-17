"""Main window for archive comparison."""

import logging
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from pk2api import Pk2Stream, ComparisonResult

from .comparison_service import ComparisonConfig, ComparisonService, DiffItem, DiffType
from .comparison_tree import ComparisonTreeWidget
from .select_archives_dialog import SelectArchivesDialog
from .workers import CompareWorker, CopyWorker
from features.text_preview.preview_widget import TextPreviewWidget
from features.tree_browser.filter_panel import FilterPanel

logger = logging.getLogger(__name__)


class ComparisonWindow(QMainWindow):
    """Dedicated window for archive comparison."""

    target_modified = pyqtSignal()
    source_modified = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Archive Comparison")
        self.setMinimumSize(800, 600)

        self._source_stream: Optional[Pk2Stream] = None
        self._target_stream: Optional[Pk2Stream] = None
        self._result: Optional[ComparisonResult] = None
        self._diff_items: list[DiffItem] = []
        self._config: Optional[ComparisonConfig] = None
        self._last_splitter_sizes: list[int] = [600, 400]

        self._setup_menu()
        self._setup_toolbar()
        self._setup_central_widget()
        self._setup_statusbar()
        self._update_ui_state()

    def _setup_menu(self) -> None:
        """Setup menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self._compare_action = QAction("&Compare Archives...", self)
        self._compare_action.triggered.connect(self._on_compare)
        file_menu.addAction(self._compare_action)

        file_menu.addSeparator()

        close_action = QAction("&Close", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self._copy_selected_action = QAction("Add &Selected to Target", self)
        self._copy_selected_action.triggered.connect(self._on_copy_selected)
        edit_menu.addAction(self._copy_selected_action)

        self._copy_all_action = QAction("Add &All to Target", self)
        self._copy_all_action.triggered.connect(self._on_copy_all)
        edit_menu.addAction(self._copy_all_action)

        edit_menu.addSeparator()

        self._restore_selected_action = QAction("Add Selected to &Source", self)
        self._restore_selected_action.triggered.connect(self._on_restore_selected)
        edit_menu.addAction(self._restore_selected_action)

    def _setup_toolbar(self) -> None:
        """Setup toolbar."""
        toolbar = QToolBar("Comparison Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._compare_btn = QAction("Compare...", self)
        self._compare_btn.triggered.connect(self._on_compare)
        toolbar.addAction(self._compare_btn)

        toolbar.addSeparator()

        self._copy_btn = QAction("Add to Target", self)
        self._copy_btn.triggered.connect(self._on_copy_selected)
        toolbar.addAction(self._copy_btn)

        self._refresh_btn = QAction("Refresh", self)
        self._refresh_btn.triggered.connect(self._on_refresh)
        toolbar.addAction(self._refresh_btn)

        toolbar.addSeparator()

        self._toggle_preview_action = QAction("Toggle Preview", self)
        self._toggle_preview_action.setCheckable(True)
        self._toggle_preview_action.setChecked(True)
        self._toggle_preview_action.triggered.connect(self._on_toggle_preview)
        toolbar.addAction(self._toggle_preview_action)

    def _setup_central_widget(self) -> None:
        """Setup central widget."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Archive info section
        info_layout = QHBoxLayout()

        source_group = QGroupBox("Source")
        source_layout = QFormLayout(source_group)
        self._source_label = QLabel("-")
        source_layout.addRow("Path:", self._source_label)
        info_layout.addWidget(source_group)

        target_group = QGroupBox("Target")
        target_layout = QFormLayout(target_group)
        self._target_label = QLabel("-")
        target_layout.addRow("Path:", self._target_label)
        info_layout.addWidget(target_group)

        layout.addLayout(info_layout)

        # Summary label
        self._summary_label = QLabel("No comparison loaded")
        self._summary_label.setStyleSheet("font-weight: bold; padding: 4px;")
        layout.addWidget(self._summary_label)

        # Filter panel
        self._filter_panel = FilterPanel()
        self._filter_panel.setFixedHeight(30)
        layout.addWidget(self._filter_panel)

        # Splitter for tree and preview
        self._splitter = QSplitter(Qt.Orientation.Vertical)

        # Comparison tree
        self._tree_widget = ComparisonTreeWidget()
        self._tree_widget.item_selected.connect(self._on_item_selected)
        self._tree_widget.copy_requested.connect(self._on_copy_items)
        self._tree_widget.restore_requested.connect(self._on_restore_items)
        self._filter_panel.filters_changed.connect(
            self._tree_widget.apply_content_filter
        )
        self._splitter.addWidget(self._tree_widget)

        # Preview widget
        self._preview_widget = TextPreviewWidget()
        self._splitter.addWidget(self._preview_widget)

        # Set initial splitter sizes (60% tree, 40% preview)
        self._splitter.setSizes([600, 400])
        layout.addWidget(self._splitter, 1)

        # Details panel
        details_group = QGroupBox("Details")
        details_layout = QFormLayout(details_group)
        self._detail_path_label = QLabel("-")
        self._detail_status_label = QLabel("-")
        self._detail_source_size_label = QLabel("-")
        self._detail_target_size_label = QLabel("-")
        details_layout.addRow("Path:", self._detail_path_label)
        details_layout.addRow("Status:", self._detail_status_label)
        details_layout.addRow("Source Size:", self._detail_source_size_label)
        details_layout.addRow("Target Size:", self._detail_target_size_label)
        details_group.setMaximumHeight(130)
        layout.addWidget(details_group)

    def _setup_statusbar(self) -> None:
        """Setup status bar."""
        self._statusbar = self.statusBar()
        self._statusbar.showMessage("Select archives to compare")

    def _update_ui_state(self) -> None:
        """Update UI based on current state."""
        has_result = self._result is not None
        has_selection = len(self._tree_widget.get_selected_items()) > 0
        has_copyable = len(self._tree_widget.get_copyable_items()) > 0
        has_restorable = len(self._tree_widget.get_restorable_items()) > 0

        self._copy_selected_action.setEnabled(has_result and has_copyable)
        self._copy_all_action.setEnabled(has_result)
        self._copy_btn.setEnabled(has_result and has_copyable)
        self._restore_selected_action.setEnabled(has_result and has_restorable)
        self._refresh_btn.setEnabled(has_result)

    def _on_toggle_preview(self, checked: bool) -> None:
        """Toggle preview panel visibility."""
        if checked:
            self._preview_widget.show()
            self._splitter.setSizes(self._last_splitter_sizes)
        else:
            self._last_splitter_sizes = self._splitter.sizes()
            self._preview_widget.hide()

    def _on_compare(self) -> None:
        """Handle compare action - show dialog and run comparison."""
        dialog = SelectArchivesDialog(self)
        if dialog.exec():
            self._config = dialog.config
            self._run_comparison(self._config)

    def _run_comparison(self, config: ComparisonConfig) -> None:
        """Run comparison in background thread."""
        # Use indeterminate progress since block count estimation is inaccurate
        self._progress = QProgressDialog("Comparing archives...", None, 0, 0, self)
        self._progress.setWindowTitle("Comparing Archives")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setCancelButton(None)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        # Throttle progress updates to avoid UI flickering
        self._last_progress_update = 0.0
        self._progress_throttle_ms = 250  # Update at most every 50ms

        self._compare_worker = CompareWorker(config, self)
        self._compare_worker.progress.connect(self._on_compare_progress)
        self._compare_worker.finished.connect(self._on_compare_finished)
        self._compare_worker.error.connect(self._on_compare_error)
        self._compare_worker.start()

    def _on_compare_progress(
        self, stage: str, current: int, total: int, elapsed: float
    ) -> None:
        """Handle comparison progress update with throttling."""
        now = time.time() * 1000  # Current time in ms

        # Throttle updates for rapid file comparisons
        # Always update for stage changes (non-Comparing stages)
        is_file_comparison = stage.startswith("Comparing:")
        if is_file_comparison:
            if now - self._last_progress_update < self._progress_throttle_ms:
                return
        self._last_progress_update = now

        # Format elapsed time
        if elapsed < 60:
            time_text = f"{elapsed:.1f}s"
        else:
            time_text = f"{elapsed / 60:.1f}m"

        # For comparison stage (has accurate total), show progress
        if is_file_comparison and total > 0:
            self._progress.setLabelText(f"{stage} ({current}/{total}, {time_text})")
        elif current > 0:
            self._progress.setLabelText(f"{stage} ({current} blocks, {time_text})")
        else:
            self._progress.setLabelText(stage)

    def _on_compare_finished(self, result: ComparisonResult) -> None:
        """Handle comparison completion."""
        self._progress.close()

        self._source_stream = self._compare_worker.source_stream
        self._target_stream = self._compare_worker.target_stream
        self._result = result
        self._compare_worker.deleteLater()

        self._process_result(result)

    def _on_compare_error(self, error: str) -> None:
        """Handle comparison error."""
        self._progress.close()
        self._compare_worker.deleteLater()
        QMessageBox.critical(self, "Comparison Error", error)

    def _populate_missing_sizes(self) -> None:
        """Fill in missing file sizes by looking them up from the streams."""
        for item in self._diff_items:
            if item.is_folder:
                continue

            # For "Only in Source" (ADDED): get source size if missing
            if item.diff_type == DiffType.ADDED and item.source_size is None:
                if self._source_stream:
                    try:
                        file = self._source_stream.get_file(item.path)
                        if file:
                            item.source_size = file.size
                    except Exception:
                        pass

            # For "Only in Target" (REMOVED): get target size if missing
            elif item.diff_type == DiffType.REMOVED and item.target_size is None:
                if self._target_stream:
                    try:
                        file = self._target_stream.get_file(item.path)
                        if file:
                            item.target_size = file.size
                    except Exception:
                        pass

    def _process_result(self, result: ComparisonResult) -> None:
        """Process and display comparison result."""
        service = ComparisonService()
        service._result = result
        self._diff_items = service.get_diff_items()

        # Fill in missing sizes from streams (pk2api doesn't always provide them)
        self._populate_missing_sizes()

        self._tree_widget.populate(self._diff_items)

        source_path = (
            str(Path(self._config.source_path).resolve()) if self._config else "-"
        )
        target_path = (
            str(Path(self._config.target_path).resolve()) if self._config else "-"
        )
        self._source_label.setText(source_path)
        self._target_label.setText(target_path)

        summary = self._tree_widget.get_summary()
        total_changes = summary["added"] + summary["removed"] + summary["modified"]

        parts = []
        if summary["added"] > 0:
            parts.append(f"{summary['added']} only in source")
        if summary["removed"] > 0:
            parts.append(f"{summary['removed']} only in target")
        if summary["modified"] > 0:
            parts.append(f"{summary['modified']} modified")
        if summary["unchanged"] > 0:
            parts.append(f"{summary['unchanged']} unchanged")

        if not parts:
            self._summary_label.setText("Archives are empty")
        else:
            self._summary_label.setText(", ".join(parts))

        self._statusbar.showMessage(
            f"Comparison complete: {total_changes} differences found"
        )
        self._update_ui_state()

    def _on_item_selected(self, item: DiffItem) -> None:
        """Handle item selection in tree."""
        self._detail_path_label.setText(item.path)
        self._detail_status_label.setText(item.diff_type.value.capitalize())

        # Get sizes - fall back to looking up from streams if not in DiffItem
        source_size = item.source_size
        target_size = item.target_size

        if not item.is_folder:
            # For "Only in Source" items, ensure we have source size
            if (
                source_size is None
                and item.diff_type == DiffType.ADDED
                and self._source_stream
            ):
                try:
                    file = self._source_stream.get_file(item.path)
                    if file:
                        source_size = file.size
                except Exception:
                    pass

            # For "Only in Target" items, ensure we have target size
            if (
                target_size is None
                and item.diff_type == DiffType.REMOVED
                and self._target_stream
            ):
                try:
                    file = self._target_stream.get_file(item.path)
                    if file:
                        target_size = file.size
                except Exception:
                    pass

        self._detail_source_size_label.setText(self._format_size(source_size))
        self._detail_target_size_label.setText(self._format_size(target_size))
        self._update_ui_state()

        # Update preview
        self._update_preview(item)

    def _update_preview(self, item: DiffItem) -> None:
        """Update the preview widget with the selected item."""
        if item.is_folder:
            self._preview_widget.clear_preview()
            return

        # Choose which stream to read from based on diff type
        # ADDED/MODIFIED: file exists in source
        # REMOVED/UNCHANGED: file exists in target
        if item.diff_type in (DiffType.ADDED, DiffType.MODIFIED):
            stream = self._source_stream
        else:
            stream = self._target_stream

        if not stream:
            self._preview_widget.clear_preview()
            return

        try:
            file = stream.get_file(item.path)
            if file:
                self._preview_widget.preview_file(file)
            else:
                self._preview_widget.clear_preview()
        except Exception:
            logger.exception("Failed to preview file: %s", item.path)
            self._preview_widget.clear_preview()

    def _on_copy_selected(self) -> None:
        """Copy selected items to target."""
        items = self._tree_widget.get_copyable_items()
        if items:
            self._on_copy_items(items)

    def _on_copy_all(self) -> None:
        """Copy all changed items to target."""
        items = self._tree_widget.get_all_copyable_items()
        if items:
            reply = QMessageBox.question(
                self,
                "Confirm Add",
                f"Add {len(items)} items to target archive?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_copy_items(items)

    def _on_copy_items(self, items: list[tuple[str, bool]]) -> None:
        """Copy items from source to target."""
        if not self._source_stream or not self._target_stream:
            QMessageBox.warning(self, "Error", "Archives not loaded")
            return

        # Store items for update after copy
        self._pending_copy_items = items

        self._copy_progress = QProgressDialog(
            "Adding files...", "Cancel", 0, len(items), self
        )
        self._copy_progress.setWindowTitle("Adding to Target")
        self._copy_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._copy_progress.setMinimumDuration(0)
        self._copy_progress.setValue(0)
        self._copy_progress.show()

        self._copy_worker = CopyWorker(
            self._source_stream, self._target_stream, items, self
        )
        self._copy_worker.progress.connect(self._on_copy_progress)
        self._copy_worker.finished.connect(self._on_copy_finished)
        self._copy_progress.canceled.connect(self._copy_worker.terminate)
        self._copy_worker.start()

    def _on_copy_progress(self, current: int, total: int) -> None:
        """Handle copy progress update."""
        self._copy_progress.setValue(current)
        self._copy_progress.setLabelText(f"Adding files... ({current}/{total})")

    def _on_copy_finished(self, success: int, failed: int) -> None:
        """Handle copy completion."""
        self._copy_progress.close()
        self._copy_worker.deleteLater()

        if failed == 0:
            QMessageBox.information(
                self, "Complete", f"Added {success} items to target archive."
            )
        else:
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Added {success} items, {failed} failed.",
            )

        self.target_modified.emit()
        self._update_after_copy(self._pending_copy_items, to_target=True)
        self._pending_copy_items = []

    def _on_restore_selected(self) -> None:
        """Restore selected items to source."""
        items = self._tree_widget.get_restorable_items()
        if items:
            self._on_restore_items(items)

    def _on_restore_items(self, items: list[tuple[str, bool]]) -> None:
        """Restore items from target to source (reverse copy)."""
        if not self._source_stream or not self._target_stream:
            QMessageBox.warning(self, "Error", "Archives not loaded")
            return

        # Store items for update after restore
        self._pending_restore_items = items

        self._restore_progress = QProgressDialog(
            "Adding files...", "Cancel", 0, len(items), self
        )
        self._restore_progress.setWindowTitle("Adding to Source")
        self._restore_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._restore_progress.setMinimumDuration(0)
        self._restore_progress.setValue(0)
        self._restore_progress.show()

        # Swap source and target for restore operation
        self._restore_worker = CopyWorker(
            self._target_stream, self._source_stream, items, self
        )
        self._restore_worker.progress.connect(self._on_restore_progress)
        self._restore_worker.finished.connect(self._on_restore_finished)
        self._restore_progress.canceled.connect(self._restore_worker.terminate)
        self._restore_worker.start()

    def _on_restore_progress(self, current: int, total: int) -> None:
        """Handle restore progress update."""
        self._restore_progress.setValue(current)
        self._restore_progress.setLabelText(f"Adding files... ({current}/{total})")

    def _on_restore_finished(self, success: int, failed: int) -> None:
        """Handle restore completion."""
        self._restore_progress.close()
        self._restore_worker.deleteLater()

        if failed == 0:
            QMessageBox.information(
                self, "Complete", f"Added {success} items to source archive."
            )
        else:
            QMessageBox.warning(
                self,
                "Partial Success",
                f"Added {success} items, {failed} failed.",
            )

        self.source_modified.emit()
        self._update_after_copy(self._pending_restore_items, to_target=False)
        self._pending_restore_items = []

    def _update_after_copy(
        self, items: list[tuple[str, bool]], to_target: bool
    ) -> None:
        """Update diff items after copy without re-comparing.

        Args:
            items: List of (path, is_folder) tuples that were copied
            to_target: True if copied to target, False if copied to source
        """
        copied_paths = {path for path, _ in items}

        for diff_item in self._diff_items:
            if diff_item.path not in copied_paths:
                continue

            if to_target:
                # Copied from source to target
                # ADDED (only in source) -> UNCHANGED (now in both)
                # MODIFIED -> UNCHANGED (now same in both)
                if diff_item.diff_type in (DiffType.ADDED, DiffType.MODIFIED):
                    diff_item.diff_type = DiffType.UNCHANGED
                    # Target now has same content as source
                    diff_item.target_size = diff_item.source_size
            else:
                # Copied from target to source (restore)
                # REMOVED (only in target) -> UNCHANGED (now in both)
                if diff_item.diff_type == DiffType.REMOVED:
                    diff_item.diff_type = DiffType.UNCHANGED
                    # Source now has same content as target
                    diff_item.source_size = diff_item.target_size

        # Rebuild tree with updated items
        self._tree_widget.populate(self._diff_items)

        # Update summary
        summary = self._tree_widget.get_summary()
        parts = []
        if summary["added"] > 0:
            parts.append(f"{summary['added']} only in source")
        if summary["removed"] > 0:
            parts.append(f"{summary['removed']} only in target")
        if summary["modified"] > 0:
            parts.append(f"{summary['modified']} modified")
        if summary["unchanged"] > 0:
            parts.append(f"{summary['unchanged']} unchanged")

        if not parts:
            self._summary_label.setText("Archives are identical")
        else:
            self._summary_label.setText(", ".join(parts))

        self._update_ui_state()

    def _on_refresh(self) -> None:
        """Refresh comparison."""
        if self._config and self._source_stream and self._target_stream:
            self._run_comparison(self._config)

    def _format_size(self, size: Optional[int]) -> str:
        """Format file size for display."""
        if size is None:
            return "-"
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def closeEvent(self, event) -> None:
        """Handle window close."""
        if self._source_stream:
            self._source_stream.close()
            self._source_stream = None
        if self._target_stream:
            self._target_stream.close()
            self._target_stream = None
        event.accept()
