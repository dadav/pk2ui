"""Dialog for selecting source and target archives for comparison."""

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .comparison_service import ComparisonConfig


class SelectArchivesDialog(QDialog):
    """Dialog for selecting two PK2 archives to compare."""

    DEFAULT_KEY = "169841"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Archives")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Source archive group
        source_group = QGroupBox("Source Archive")
        source_layout = QVBoxLayout(source_group)

        source_file_layout = QHBoxLayout()
        self._source_path_edit = QLineEdit()
        self._source_path_edit.setPlaceholderText("Select source PK2 file...")
        source_browse_btn = QPushButton("Browse...")
        source_browse_btn.clicked.connect(self._browse_source)
        source_file_layout.addWidget(self._source_path_edit)
        source_file_layout.addWidget(source_browse_btn)
        source_layout.addLayout(source_file_layout)

        source_form = QFormLayout()
        self._source_key_edit = QLineEdit(self.DEFAULT_KEY)
        source_form.addRow("Encryption Key:", self._source_key_edit)
        source_layout.addLayout(source_form)

        layout.addWidget(source_group)

        # Target archive group
        target_group = QGroupBox("Target Archive")
        target_layout = QVBoxLayout(target_group)

        target_file_layout = QHBoxLayout()
        self._target_path_edit = QLineEdit()
        self._target_path_edit.setPlaceholderText("Select target PK2 file...")
        target_browse_btn = QPushButton("Browse...")
        target_browse_btn.clicked.connect(self._browse_target)
        target_file_layout.addWidget(self._target_path_edit)
        target_file_layout.addWidget(target_browse_btn)
        target_layout.addLayout(target_file_layout)

        target_form = QFormLayout()
        self._target_key_edit = QLineEdit(self.DEFAULT_KEY)
        target_form.addRow("Encryption Key:", self._target_key_edit)
        target_layout.addLayout(target_form)

        layout.addWidget(target_group)

        # Options
        options_form = QFormLayout()
        self._compute_hashes_check = QCheckBox()
        self._compute_hashes_check.setChecked(True)
        options_form.addRow("Compute file hashes:", self._compute_hashes_check)
        layout.addLayout(options_form)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        compare_btn = QPushButton("Compare")
        compare_btn.setDefault(True)
        compare_btn.clicked.connect(self._validate_and_accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(compare_btn)
        layout.addLayout(btn_layout)

    def _browse_source(self) -> None:
        """Open file browser for source archive."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Source PK2 Archive",
            "",
            "PK2 Archives (*.pk2);;All Files (*)",
        )
        if path:
            self._source_path_edit.setText(path)

    def _browse_target(self) -> None:
        """Open file browser for target archive."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Target PK2 Archive",
            "",
            "PK2 Archives (*.pk2);;All Files (*)",
        )
        if path:
            self._target_path_edit.setText(path)

    def _validate_and_accept(self) -> None:
        """Validate inputs and accept dialog."""
        if not self._source_path_edit.text():
            self._source_path_edit.setFocus()
            return
        if not self._target_path_edit.text():
            self._target_path_edit.setFocus()
            return
        self.accept()

    @property
    def source_path(self) -> str:
        return self._source_path_edit.text()

    @property
    def source_key(self) -> str:
        return self._source_key_edit.text()

    @property
    def target_path(self) -> str:
        return self._target_path_edit.text()

    @property
    def target_key(self) -> str:
        return self._target_key_edit.text()

    @property
    def compute_hashes(self) -> bool:
        return self._compute_hashes_check.isChecked()

    @property
    def config(self) -> ComparisonConfig:
        """Get comparison configuration from dialog inputs."""
        return ComparisonConfig(
            source_path=self.source_path,
            source_key=self.source_key,
            target_path=self.target_path,
            target_key=self.target_key,
            compute_hashes=self.compute_hashes,
        )
