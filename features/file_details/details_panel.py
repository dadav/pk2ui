"""Panel for displaying file/folder details."""

from PyQt6.QtWidgets import QFormLayout, QLabel, QVBoxLayout, QWidget
from pk2api import Pk2File, Pk2Folder


class DetailsPanel(QWidget):
    """Displays details about selected file or folder."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._name_label = QLabel("-")
        self._type_label = QLabel("-")
        self._size_label = QLabel("-")
        self._path_label = QLabel("-")
        self._path_label.setWordWrap(True)

        form.addRow("Name:", self._name_label)
        form.addRow("Type:", self._type_label)
        form.addRow("Size:", self._size_label)
        form.addRow("Path:", self._path_label)

        layout.addLayout(form)
        layout.addStretch()

    def show_file(self, file: Pk2File) -> None:
        """Display file details."""
        self._name_label.setText(file.name)
        self._type_label.setText("File")
        self._size_label.setText(self._format_size(file.size))
        self._path_label.setText(file.get_full_path())

    def show_folder(self, folder: Pk2Folder) -> None:
        """Display folder details."""
        self._name_label.setText(folder.name or "(root)")
        self._type_label.setText("Folder")
        file_count = len(folder.files)
        folder_count = len(folder.folders)
        self._size_label.setText(f"{file_count} files, {folder_count} folders")
        self._path_label.setText(folder.get_full_path() or "/")

    def clear(self) -> None:
        """Clear all details."""
        self._name_label.setText("-")
        self._type_label.setText("-")
        self._size_label.setText("-")
        self._path_label.setText("-")

    def _format_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB ({size:,} bytes)"
        else:
            return f"{size / (1024 * 1024):.1f} MB ({size:,} bytes)"
