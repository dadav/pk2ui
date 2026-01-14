"""Tree widget for displaying archive comparison results with diff highlighting."""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .comparison_service import DiffItem, DiffType

logger = logging.getLogger(__name__)


class DiffTreeItemData:
    """Data stored with each tree item."""

    def __init__(self, path: str, is_folder: bool, diff_type: DiffType) -> None:
        self.path = path
        self.is_folder = is_folder
        self.diff_type = diff_type


class ComparisonTreeWidget(QWidget):
    """Tree widget showing comparison results with diff highlighting."""

    item_selected = pyqtSignal(object)
    items_selected = pyqtSignal(list)
    copy_requested = pyqtSignal(list)

    COLORS = {
        DiffType.ADDED: QColor("#2d5a2d"),
        DiffType.REMOVED: QColor("#5a2d2d"),
        DiffType.MODIFIED: QColor("#5a5a2d"),
        DiffType.UNCHANGED: None,
    }

    ICONS = {
        DiffType.ADDED: "+",
        DiffType.REMOVED: "-",
        DiffType.MODIFIED: "~",
        DiffType.UNCHANGED: " ",
    }

    STATUS_TEXT = {
        DiffType.ADDED: "Added",
        DiffType.REMOVED: "Removed",
        DiffType.MODIFIED: "Modified",
        DiffType.UNCHANGED: "Same",
    }

    def __init__(self) -> None:
        super().__init__()
        self._diff_items: list[DiffItem] = []
        self._current_filter: Optional[DiffType] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(
            ["All", "Added", "Removed", "Modified", "Unchanged"]
        )
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self._filter_combo)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["", "Name", "Source Size", "Target Size", "Status"])
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setColumnWidth(0, 30)
        self._tree.setColumnWidth(1, 300)
        self._tree.setColumnWidth(2, 100)
        self._tree.setColumnWidth(3, 100)
        self._tree.setColumnWidth(4, 80)
        self._tree.setSortingEnabled(True)
        self._tree.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        layout.addWidget(self._tree)

    def populate(self, diff_items: list[DiffItem]) -> None:
        """Populate tree with diff items."""
        logger.info("Populating comparison tree with %d items", len(diff_items))
        self._diff_items = diff_items
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Rebuild the tree with current filter."""
        self._tree.clear()

        # Build path hierarchy
        path_items: dict[str, QTreeWidgetItem] = {}

        for diff_item in self._diff_items:
            if not self._passes_filter(diff_item):
                continue

            parts = diff_item.path.split("/")
            current_path = ""

            for i, part in enumerate(parts):
                parent_path = current_path
                current_path = f"{current_path}/{part}" if current_path else part
                is_last = i == len(parts) - 1

                if current_path in path_items:
                    continue

                if is_last:
                    item = self._create_tree_item(diff_item, part)
                else:
                    item = self._create_folder_item(part, current_path)

                path_items[current_path] = item

                if parent_path and parent_path in path_items:
                    path_items[parent_path].addChild(item)
                else:
                    self._tree.addTopLevelItem(item)

        self._tree.expandAll()

    def _create_tree_item(self, diff_item: DiffItem, name: str) -> QTreeWidgetItem:
        """Create tree item for a diff item."""
        icon = self.ICONS.get(diff_item.diff_type, " ")
        source_size = self._format_size(diff_item.source_size)
        target_size = self._format_size(diff_item.target_size)
        status = self.STATUS_TEXT.get(diff_item.diff_type, "")

        item = QTreeWidgetItem([icon, name, source_size, target_size, status])
        data = DiffTreeItemData(diff_item.path, diff_item.is_folder, diff_item.diff_type)
        item.setData(0, Qt.ItemDataRole.UserRole, data)

        color = self.COLORS.get(diff_item.diff_type)
        if color:
            for col in range(5):
                item.setBackground(col, QBrush(color))

        return item

    def _create_folder_item(self, name: str, path: str) -> QTreeWidgetItem:
        """Create tree item for an intermediate folder."""
        item = QTreeWidgetItem([" ", name, "", "", "Folder"])
        data = DiffTreeItemData(path, True, DiffType.UNCHANGED)
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        return item

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

    def _passes_filter(self, diff_item: DiffItem) -> bool:
        """Check if item passes current filter."""
        if self._current_filter is None:
            return True
        return diff_item.diff_type == self._current_filter

    def _on_filter_changed(self, index: int) -> None:
        """Handle filter dropdown change."""
        filter_map = {
            0: None,
            1: DiffType.ADDED,
            2: DiffType.REMOVED,
            3: DiffType.MODIFIED,
            4: DiffType.UNCHANGED,
        }
        self._current_filter = filter_map.get(index)
        self._rebuild_tree()

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        items = self._tree.selectedItems()

        if not items:
            return

        selected_data = []
        for item in items:
            data: DiffTreeItemData = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                diff_item = self._find_diff_item(data.path)
                if diff_item:
                    selected_data.append(diff_item)

        if len(selected_data) == 1:
            self.item_selected.emit(selected_data[0])
        elif selected_data:
            self.items_selected.emit(selected_data)

    def _find_diff_item(self, path: str) -> Optional[DiffItem]:
        """Find DiffItem by path."""
        for item in self._diff_items:
            if item.path == path:
                return item
        return None

    def _show_context_menu(self, position) -> None:
        """Show context menu for tree item."""
        item = self._tree.itemAt(position)
        if not item:
            return

        selected_items = self._tree.selectedItems()
        menu = QMenu(self)

        copyable_items = []
        for sel_item in selected_items:
            data: DiffTreeItemData = sel_item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.diff_type in (DiffType.ADDED, DiffType.MODIFIED):
                copyable_items.append((data.path, data.is_folder))

        if copyable_items:
            if len(copyable_items) == 1:
                copy_action = QAction("Copy to Target", self)
            else:
                copy_action = QAction(f"Copy {len(copyable_items)} items to Target", self)
            copy_action.triggered.connect(lambda: self.copy_requested.emit(copyable_items))
            menu.addAction(copy_action)
        else:
            info_action = QAction("(No copyable items selected)", self)
            info_action.setEnabled(False)
            menu.addAction(info_action)

        menu.exec(self._tree.mapToGlobal(position))

    def get_selected_items(self) -> list[tuple[str, bool]]:
        """Get all selected items as list of (path, is_folder) tuples."""
        result = []
        for item in self._tree.selectedItems():
            data: DiffTreeItemData = item.data(0, Qt.ItemDataRole.UserRole)
            if data is not None:
                result.append((data.path, data.is_folder))
        return result

    def get_copyable_items(self) -> list[tuple[str, bool]]:
        """Get items that can be copied (ADDED or MODIFIED)."""
        result = []
        for item in self._tree.selectedItems():
            data: DiffTreeItemData = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.diff_type in (DiffType.ADDED, DiffType.MODIFIED):
                result.append((data.path, data.is_folder))
        return result

    def get_all_copyable_items(self) -> list[tuple[str, bool]]:
        """Get all items that can be copied (ADDED or MODIFIED from source)."""
        result = []
        for diff_item in self._diff_items:
            if diff_item.diff_type in (DiffType.ADDED, DiffType.MODIFIED):
                result.append((diff_item.path, diff_item.is_folder))
        return result

    def get_summary(self) -> dict[str, int]:
        """Get summary counts of diff types."""
        summary = {
            "added": 0,
            "removed": 0,
            "modified": 0,
            "unchanged": 0,
        }
        for item in self._diff_items:
            if item.diff_type == DiffType.ADDED:
                summary["added"] += 1
            elif item.diff_type == DiffType.REMOVED:
                summary["removed"] += 1
            elif item.diff_type == DiffType.MODIFIED:
                summary["modified"] += 1
            else:
                summary["unchanged"] += 1
        return summary
