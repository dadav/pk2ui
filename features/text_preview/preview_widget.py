"""Text preview widget for text-based files."""

import logging

from PyQt6.QtWidgets import QPlainTextEdit
from pk2api import Pk2File

logger = logging.getLogger(__name__)

# File extensions that can be previewed as text
TEXT_EXTENSIONS = {
    ".txt",
    ".ini",
    ".xml",
    ".cfg",
    ".log",
    ".json",
    ".csv",
    ".html",
    ".htm",
    ".md",
    ".yaml",
    ".yml",
}


class TextPreviewWidget(QPlainTextEdit):
    """Preview widget for text-based files."""

    MAX_PREVIEW_SIZE = 512 * 1024  # 512 KB max preview

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("Select a text file to preview")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def preview_file(self, file: Pk2File) -> None:
        """Preview file content if it's a text file."""
        ext = self._get_extension(file.name)

        if ext not in TEXT_EXTENSIONS:
            self.setPlainText(f"[Binary file: {file.name}]")
            return

        if file.size > self.MAX_PREVIEW_SIZE:
            self.setPlainText(f"[File too large for preview: {file.size:,} bytes]")
            return

        try:
            content = file.get_content()
            # Try UTF-8 first, fall back to latin-1
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1")
            self.setPlainText(text)
            logger.debug("Previewed file: %s (%d bytes)", file.name, len(content))
        except Exception as e:
            logger.exception("Preview failed: %s", file.name)
            self.setPlainText(f"[Error reading file: {e}]")

    def clear_preview(self) -> None:
        """Clear the preview."""
        self.clear()

    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        if "." in filename:
            return "." + filename.rsplit(".", 1)[1].lower()
        return ""
