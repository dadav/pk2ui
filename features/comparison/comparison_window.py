"""Main window for archive comparison."""

import logging
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)
from pk2api import Pk2Stream, ComparisonResult

from .comparison_service import ComparisonConfig, ComparisonService, DiffItem, DiffType
from .comparison_tree import ComparisonTreeWidget
from .select_archives_dialog import SelectArchivesDialog
from .workers import CompareWorker, CopyWorker

logger = logging.getLogger(__name__)


class ComparisonWindow(QMainWindow):
    """Dedicated window for archive comparison."""

    target_modified = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Archive Comparison")
        self.setMinimumSize(800, 600)

        self._source_stream: Optional[Pk2Stream] = None
        self._target_stream: Optional[Pk2Stream] = None
        self._result: Optional[ComparisonResult] = None
        self._diff_items: list[DiffItem] = []
        self._config: Optional[ComparisonConfig] = None

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

        self._copy_selected_action = QAction("Copy &Selected to Target", self)
        self._copy_selected_action.triggered.connect(self._on_copy_selected)
        edit_menu.addAction(self._copy_selected_action)

        self._copy_all_action = QAction("Copy &All Changes to Target", self)
        self._copy_all_action.triggered.connect(self._on_copy_all)
        edit_menu.addAction(self._copy_all_action)

    def _setup_toolbar(self) -> None:
        """Setup toolbar."""
        toolbar = QToolBar("Comparison Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        self._compare_btn = QAction("Compare...", self)
        self._compare_btn.triggered.connect(self._on_compare)
        toolbar.addAction(self._compare_btn)

        toolbar.addSeparator()

        self._copy_btn = QAction("Copy to Target", self)
        self._copy_btn.triggered.connect(self._on_copy_selected)
        toolbar.addAction(self._copy_btn)

        self._refresh_btn = QAction("Refresh", self)
        self._refresh_btn.triggered.connect(self._on_refresh)
        toolbar.addAction(self._refresh_btn)

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

        # Comparison tree
        self._tree_widget = ComparisonTreeWidget()
        self._tree_widget.item_selected.connect(self._on_item_selected)
        self._tree_widget.copy_requested.connect(self._on_copy_items)
        layout.addWidget(self._tree_widget, 1)

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

        self._copy_selected_action.setEnabled(has_result and has_copyable)
        self._copy_all_action.setEnabled(has_result)
        self._copy_btn.setEnabled(has_result and has_copyable)
        self._refresh_btn.setEnabled(has_result)

    def _on_compare(self) -> None:
        """Handle compare action - show dialog and run comparison."""
        dialog = SelectArchivesDialog(self)
        if dialog.exec():
            self._config = dialog.config
            self._run_comparison(self._config)

    def _run_comparison(self, config: ComparisonConfig) -> None:
        """Run comparison in background thread."""
        self._progress = QProgressDialog("Comparing archives...", None, 0, 0, self)
        self._progress.setWindowTitle("Please Wait")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setCancelButton(None)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        self._compare_worker = CompareWorker(config, self)
        self._compare_worker.finished.connect(self._on_compare_finished)
        self._compare_worker.error.connect(self._on_compare_error)
        self._compare_worker.start()

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

    def _process_result(self, result: ComparisonResult) -> None:
        """Process and display comparison result."""
        service = ComparisonService()
        service._result = result
        self._diff_items = service.get_diff_items()

        self._tree_widget.populate(self._diff_items)

        source_name = Path(self._config.source_path).name if self._config else "-"
        target_name = Path(self._config.target_path).name if self._config else "-"
        self._source_label.setText(source_name)
        self._target_label.setText(target_name)

        summary = self._tree_widget.get_summary()
        self._summary_label.setText(
            f"{summary['added']} added, {summary['removed']} removed, "
            f"{summary['modified']} modified, {summary['unchanged']} unchanged"
        )

        self._statusbar.showMessage(
            f"Comparison complete: {len(self._diff_items)} items"
        )
        self._update_ui_state()

    def _on_item_selected(self, item: DiffItem) -> None:
        """Handle item selection in tree."""
        self._detail_path_label.setText(item.path)
        self._detail_status_label.setText(item.diff_type.value.capitalize())
        self._detail_source_size_label.setText(self._format_size(item.source_size))
        self._detail_target_size_label.setText(self._format_size(item.target_size))
        self._update_ui_state()

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
                "Confirm Copy",
                f"Copy {len(items)} items to target archive?",
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

        self._copy_progress = QProgressDialog(
            "Copying files...", "Cancel", 0, len(items), self
        )
        self._copy_progress.setWindowTitle("Copying")
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
        self._copy_progress.setLabelText(f"Copying files... ({current}/{total})")

    def _on_copy_finished(self, success: int, failed: int) -> None:
        """Handle copy completion."""
        self._copy_progress.close()
        self._copy_worker.deleteLater()

        if failed == 0:
            QMessageBox.information(
                self, "Copy Complete", f"Copied {success} items to target archive."
            )
        else:
            QMessageBox.warning(
                self,
                "Copy Partial",
                f"Copied {success} items, {failed} failed.",
            )

        self.target_modified.emit()
        self._on_refresh()

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
