"""Tree widget for PK2 archive navigation."""

import fnmatch
import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem
from pk2api import Pk2File, Pk2Folder

from features.tree_browser.filter_panel import FilterCriteria

logger = logging.getLogger(__name__)


class TreeItemData:
    """Data stored with each tree item."""

    def __init__(
        self, pk2_path: str, is_folder: bool, pk2_object: Pk2Folder | Pk2File
    ) -> None:
        self.pk2_path = pk2_path
        self.is_folder = is_folder
        self.pk2_object = pk2_object


class Pk2TreeWidget(QTreeWidget):
    """Tree widget for browsing PK2 archive contents."""

    # Signals
    file_selected = pyqtSignal(object)  # Pk2File
    folder_selected = pyqtSignal(object)  # Pk2Folder
    selection_changed = pyqtSignal(int)  # number of selected items
    extract_requested = pyqtSignal(str, bool)  # path, is_folder (single item)
    extract_multiple_requested = pyqtSignal(list)  # list of (path, is_folder) tuples
    delete_requested = pyqtSignal(str, bool)  # path, is_folder
    delete_multiple_requested = pyqtSignal(list)  # list of (path, is_folder) tuples
    import_requested = pyqtSignal(str)  # target folder path
    import_folder_requested = pyqtSignal(str)  # target folder path
    new_folder_requested = pyqtSignal(str)  # parent folder path

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabels(["Name", "Size", "Type"])
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.setColumnWidth(0, 250)
        self.setColumnWidth(1, 80)
        self.setColumnWidth(2, 80)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Enable multi-selection with Ctrl/Shift
        self.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)

        # Store root folder for filtering
        self._root_folder: Optional[Pk2Folder] = None
        self._current_filter: Optional[FilterCriteria] = None

    def populate(self, root_folder: Pk2Folder) -> None:
        """Populate tree from root folder."""
        logger.info("Populating tree from root folder")
        self._root_folder = root_folder
        self._rebuild_tree()

    def apply_filter(self, criteria: FilterCriteria) -> None:
        """Apply filter criteria and rebuild tree."""
        self._current_filter = criteria
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Rebuild the tree with current filter."""
        self.clear()
        if self._root_folder:
            self._add_folder_contents(None, self._root_folder, "")

    def _add_folder_contents(
        self,
        parent_item: Optional[QTreeWidgetItem],
        folder: Pk2Folder,
        path_prefix: str,
    ) -> None:
        """Recursively add folder contents to tree."""
        # Add subfolders first
        for name, subfolder in sorted(folder.folders.items()):
            if not self._folder_passes_filter(name, subfolder):
                continue

            # Use original_name for display (pk2api 1.1.0 case preservation)
            display_name = getattr(subfolder, "original_name", None) or subfolder.name or name
            # Use get_original_path if available for accurate path
            original_path = getattr(subfolder, "get_original_path", None)
            full_path = original_path() if original_path else (
                f"{path_prefix}/{display_name}" if path_prefix else display_name
            )
            item = QTreeWidgetItem([display_name, "", "Folder"])
            data = TreeItemData(full_path, True, subfolder)
            item.setData(0, Qt.ItemDataRole.UserRole, data)

            if parent_item:
                parent_item.addChild(item)
            else:
                self.addTopLevelItem(item)

            self._add_folder_contents(item, subfolder, full_path)

        # Add files
        for name, file in sorted(folder.files.items()):
            if not self._file_passes_filter(name, file):
                continue

            # Use original_name for display (pk2api 1.1.0 case preservation)
            display_name = getattr(file, "original_name", None) or file.name or name
            # Use get_original_path if available for accurate path
            original_path = getattr(file, "get_original_path", None)
            full_path = original_path() if original_path else (
                f"{path_prefix}/{display_name}" if path_prefix else display_name
            )
            size_str = self._format_size(file.size)
            ext = self._get_extension(display_name)
            item = QTreeWidgetItem([display_name, size_str, ext])
            data = TreeItemData(full_path, False, file)
            item.setData(0, Qt.ItemDataRole.UserRole, data)

            if parent_item:
                parent_item.addChild(item)
            else:
                self.addTopLevelItem(item)

    def _file_passes_filter(self, name: str, file: Pk2File) -> bool:
        """Check if a file passes the current filter."""
        if not self._current_filter:
            return True

        f = self._current_filter

        # Show files filter
        if not f.show_files:
            return False

        # Name filter - use fnmatch for glob patterns, substring match otherwise
        if f.name_pattern:
            name_lower = name.lower()
            if f.is_glob_pattern:
                # Use fnmatch for glob pattern matching
                if not fnmatch.fnmatch(name_lower, f.name_pattern):
                    return False
            else:
                # Simple substring match
                if f.name_pattern not in name_lower:
                    return False

        # Type filter
        if f.file_type:
            ext = self._get_extension(name)
            allowed_exts = [e.strip() for e in f.file_type.split(",")]
            if ext not in allowed_exts:
                return False

        # Size filter
        if f.min_size is not None and file.size < f.min_size:
            return False
        if f.max_size is not None and file.size > f.max_size:
            return False

        return True

    def _folder_passes_filter(self, name: str, folder: Pk2Folder) -> bool:
        """Check if a folder passes the current filter."""
        if not self._current_filter:
            return True

        f = self._current_filter

        # Show folders filter
        if not f.show_folders:
            # Still show folder if it contains matching files
            return self._folder_has_matching_children(folder)

        # Name filter - folders pass if name matches OR contains matching children
        if f.name_pattern:
            name_lower = name.lower()
            if f.is_glob_pattern:
                # Use fnmatch for glob pattern matching
                if fnmatch.fnmatch(name_lower, f.name_pattern):
                    return True
            else:
                # Simple substring match
                if f.name_pattern in name_lower:
                    return True
            return self._folder_has_matching_children(folder)

        # Type/size filters - show folder if it has matching children
        if f.file_type or f.min_size is not None or f.max_size is not None:
            return self._folder_has_matching_children(folder)

        return True

    def _folder_has_matching_children(self, folder: Pk2Folder) -> bool:
        """Check if folder has any children that pass the filter."""
        # Check files
        for name, file in folder.files.items():
            if self._file_passes_filter(name, file):
                return True

        # Check subfolders recursively
        for name, subfolder in folder.folders.items():
            if self._folder_has_matching_children(subfolder):
                return True

        return False

    def _format_size(self, size: int) -> str:
        """Format file size for display."""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        if "." in filename:
            return "." + filename.rsplit(".", 1)[1].lower()
        return ""

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        items = self.selectedItems()
        self.selection_changed.emit(len(items))

        if not items:
            return

        # For details/preview, use the first selected item
        data: TreeItemData = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return
        if data.is_folder:
            self.folder_selected.emit(data.pk2_object)
        else:
            self.file_selected.emit(data.pk2_object)

    def _show_context_menu(self, position) -> None:
        """Show context menu for tree item."""
        item = self.itemAt(position)
        if not item:
            return

        selected_items = self.selectedItems()
        multi_select = len(selected_items) > 1

        menu = QMenu(self)

        if multi_select:
            # Multi-selection context menu
            selected_data = self.get_selected_items()
            count = len(selected_data)

            extract_action = QAction(f"Extract {count} items...", self)
            extract_action.triggered.connect(
                lambda: self.extract_multiple_requested.emit(selected_data)
            )
            menu.addAction(extract_action)

            menu.addSeparator()

            delete_action = QAction(f"Delete {count} items", self)
            delete_action.triggered.connect(
                lambda: self.delete_multiple_requested.emit(selected_data)
            )
            menu.addAction(delete_action)
        else:
            # Single selection context menu
            data: TreeItemData = item.data(0, Qt.ItemDataRole.UserRole)
            if data is None:
                return

            extract_action = QAction("Extract...", self)
            extract_action.triggered.connect(
                lambda: self.extract_requested.emit(data.pk2_path, data.is_folder)
            )
            menu.addAction(extract_action)

            if data.is_folder:
                import_action = QAction("Import File...", self)
                import_action.triggered.connect(
                    lambda: self.import_requested.emit(data.pk2_path)
                )
                menu.addAction(import_action)

                import_folder_action = QAction("Import Folder...", self)
                import_folder_action.triggered.connect(
                    lambda: self.import_folder_requested.emit(data.pk2_path)
                )
                menu.addAction(import_folder_action)

                new_folder_action = QAction("New Folder...", self)
                new_folder_action.triggered.connect(
                    lambda: self.new_folder_requested.emit(data.pk2_path)
                )
                menu.addAction(new_folder_action)

            menu.addSeparator()

            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(
                lambda: self.delete_requested.emit(data.pk2_path, data.is_folder)
            )
            menu.addAction(delete_action)

        menu.exec(self.mapToGlobal(position))

    def get_selected_items(self) -> list[tuple[str, bool]]:
        """Get all selected items as list of (path, is_folder) tuples."""
        result = []
        for item in self.selectedItems():
            data: TreeItemData = item.data(0, Qt.ItemDataRole.UserRole)
            if data is not None:
                result.append((data.pk2_path, data.is_folder))
        return result

    def get_selection_count(self) -> int:
        """Get number of selected items."""
        return len(self.selectedItems())

    def get_selected_path(self) -> Optional[str]:
        """Get the path of the first selected item."""
        items = self.selectedItems()
        if not items:
            return None
        data: TreeItemData = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return None
        return data.pk2_path

    def get_selected_is_folder(self) -> bool:
        """Check if the first selected item is a folder."""
        items = self.selectedItems()
        if not items:
            return False
        data: TreeItemData = items[0].data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return False
        return data.is_folder
