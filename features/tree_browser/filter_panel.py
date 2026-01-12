"""Filter panel for tree browser."""

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)


@dataclass
class FilterCriteria:
    """Filter criteria for tree items."""

    name_pattern: str = ""
    file_type: str = ""  # Extension filter (e.g., ".txt", ".xml")
    min_size: Optional[int] = None  # In bytes
    max_size: Optional[int] = None  # In bytes
    show_files: bool = True
    show_folders: bool = True


# Common file type categories
FILE_TYPE_CATEGORIES = {
    "All Files": "",
    "Text Files": ".txt,.ini,.cfg,.log,.md",
    "XML Files": ".xml",
    "Data Files": ".dat,.bin,.db",
    "Images": ".png,.jpg,.jpeg,.gif,.bmp,.dds",
    "Audio": ".wav,.mp3,.ogg",
    "Scripts": ".py,.lua,.js",
}


class FilterPanel(QWidget):
    """Panel with filter controls for the tree browser."""

    filters_changed = pyqtSignal(object)  # FilterCriteria

    def __init__(self) -> None:
        super().__init__()
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup the filter panel UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Name filter
        layout.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Filter by name...")
        self._name_edit.setMaximumWidth(150)
        layout.addWidget(self._name_edit)

        # Type filter
        layout.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(FILE_TYPE_CATEGORIES.keys())
        self._type_combo.setMaximumWidth(120)
        layout.addWidget(self._type_combo)

        # Size filter
        layout.addWidget(QLabel("Size:"))
        self._size_combo = QComboBox()
        self._size_combo.addItems([
            "Any Size",
            "< 1 KB",
            "< 10 KB",
            "< 100 KB",
            "< 1 MB",
            "> 1 KB",
            "> 10 KB",
            "> 100 KB",
            "> 1 MB",
        ])
        self._size_combo.setMaximumWidth(100)
        layout.addWidget(self._size_combo)

        # Show/hide options
        layout.addWidget(QLabel("Show:"))
        self._show_combo = QComboBox()
        self._show_combo.addItems(["All", "Files Only", "Folders Only"])
        self._show_combo.setMaximumWidth(100)
        layout.addWidget(self._show_combo)

        # Clear button
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setMaximumWidth(60)
        layout.addWidget(self._clear_btn)

        layout.addStretch()

    def _connect_signals(self) -> None:
        """Connect filter control signals."""
        self._name_edit.textChanged.connect(self._emit_filters)
        self._type_combo.currentIndexChanged.connect(self._emit_filters)
        self._size_combo.currentIndexChanged.connect(self._emit_filters)
        self._show_combo.currentIndexChanged.connect(self._emit_filters)
        self._clear_btn.clicked.connect(self._clear_filters)

    def _emit_filters(self) -> None:
        """Emit current filter criteria."""
        criteria = self.get_criteria()
        self.filters_changed.emit(criteria)

    def _clear_filters(self) -> None:
        """Clear all filters."""
        self._name_edit.clear()
        self._type_combo.setCurrentIndex(0)
        self._size_combo.setCurrentIndex(0)
        self._show_combo.setCurrentIndex(0)
        self._emit_filters()

    def get_criteria(self) -> FilterCriteria:
        """Get current filter criteria."""
        criteria = FilterCriteria()

        # Name filter
        criteria.name_pattern = self._name_edit.text().lower()

        # Type filter
        type_key = self._type_combo.currentText()
        criteria.file_type = FILE_TYPE_CATEGORIES.get(type_key, "")

        # Size filter
        size_text = self._size_combo.currentText()
        criteria.min_size, criteria.max_size = self._parse_size_filter(size_text)

        # Show filter
        show_text = self._show_combo.currentText()
        if show_text == "Files Only":
            criteria.show_folders = False
        elif show_text == "Folders Only":
            criteria.show_files = False

        return criteria

    def _parse_size_filter(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Parse size filter text into min/max bytes."""
        if text == "Any Size":
            return None, None
        elif text == "< 1 KB":
            return None, 1024
        elif text == "< 10 KB":
            return None, 10 * 1024
        elif text == "< 100 KB":
            return None, 100 * 1024
        elif text == "< 1 MB":
            return None, 1024 * 1024
        elif text == "> 1 KB":
            return 1024, None
        elif text == "> 10 KB":
            return 10 * 1024, None
        elif text == "> 100 KB":
            return 100 * 1024, None
        elif text == "> 1 MB":
            return 1024 * 1024, None
        return None, None
