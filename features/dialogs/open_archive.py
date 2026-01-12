"""Dialog for opening PK2 archives with key input."""

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class OpenArchiveDialog(QDialog):
    """Dialog for selecting PK2 file and entering encryption key."""

    DEFAULT_KEY = "169841"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Open PK2 Archive")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # File selection
        file_layout = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a PK2 file...")
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(self._path_edit)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # Key input
        form = QFormLayout()
        self._key_edit = QLineEdit(self.DEFAULT_KEY)
        form.addRow("Encryption Key:", self._key_edit)
        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        open_btn = QPushButton("Open")
        open_btn.setDefault(True)
        open_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(open_btn)
        layout.addLayout(btn_layout)

    def _browse(self) -> None:
        """Open file browser."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PK2 Archive", "", "PK2 Archives (*.pk2);;All Files (*)"
        )
        if path:
            self._path_edit.setText(path)

    @property
    def file_path(self) -> str:
        return self._path_edit.text()

    @property
    def encryption_key(self) -> str:
        return self._key_edit.text()


class NewFolderDialog(QDialog):
    """Dialog for creating a new folder."""

    def __init__(self, parent_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Folder")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        # Folder name input
        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Enter folder name...")
        form.addRow("Folder Name:", self._name_edit)
        layout.addLayout(form)

        # Show parent path
        self._parent_path = parent_path
        parent_display = parent_path if parent_path else "/"
        form.addRow("Parent:", QLineEdit(parent_display))

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        create_btn = QPushButton("Create")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(create_btn)
        layout.addLayout(btn_layout)

    @property
    def folder_name(self) -> str:
        return self._name_edit.text()

    @property
    def full_path(self) -> str:
        name = self.folder_name
        if self._parent_path:
            return f"{self._parent_path}/{name}"
        return name
