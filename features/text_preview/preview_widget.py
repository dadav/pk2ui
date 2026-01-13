"""Unified preview widget for text and image files."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget
from pk2api import Pk2File

from features.image_preview import DDJDecodeError, DDSDecodeError, decode_ddj, decode_dds

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

# File extensions that can be previewed as images
IMAGE_EXTENSIONS = {
    ".ddj",
    ".dds",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tga",
    ".ico",
}


class TextPreviewWidget(QWidget):
    """Preview widget for text and image files."""

    MAX_PREVIEW_SIZE = 8 * 1024 * 1024  # 8 MB max preview

    def __init__(self) -> None:
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Stacked widget to switch between text and image views
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Text view
        self._text_view = QPlainTextEdit()
        self._text_view.setReadOnly(True)
        self._text_view.setPlaceholderText("Select a file to preview")
        self._text_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._stack.addWidget(self._text_view)

        # Image view
        self._image_view = QLabel()
        self._image_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_view.setStyleSheet("QLabel { background-color: #2d2d2d; }")
        self._stack.addWidget(self._image_view)

        # Store current pixmap for resize events
        self._current_pixmap: QPixmap | None = None

    def preview_file(self, file: Pk2File) -> None:
        """Preview file content based on type."""
        if file.size > self.MAX_PREVIEW_SIZE:
            self._show_text(f"[File too large for preview: {file.size:,} bytes]")
            return

        ext = self._get_extension(file.name)

        if ext in IMAGE_EXTENSIONS:
            self._preview_image(file, ext)
        elif ext in TEXT_EXTENSIONS:
            self._preview_text(file)
        else:
            # Unknown extension - try to detect content type
            try:
                content = file.get_content()
                if self._looks_like_text(content):
                    self._show_text_content(content, file.name)
                else:
                    self._show_text(f"[Binary file: {file.name}]")
            except Exception as e:
                logger.exception("Preview failed: %s", file.name)
                self._show_text(f"[Error reading file: {e}]")

    def _preview_text(self, file: Pk2File) -> None:
        """Preview file as text."""
        try:
            content = file.get_content()
            self._show_text_content(content, file.name)
        except Exception as e:
            logger.exception("Text preview failed: %s", file.name)
            self._show_text(f"[Error reading file: {e}]")

    def _show_text_content(self, content: bytes, filename: str) -> None:
        """Show text content with encoding fallback."""
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        self._show_text(text)
        logger.debug("Previewed text file: %s (%d bytes)", filename, len(content))

    def _show_text(self, text: str) -> None:
        """Show text in text view."""
        self._current_pixmap = None
        self._text_view.setPlainText(text)
        self._stack.setCurrentWidget(self._text_view)

    def _preview_image(self, file: Pk2File, ext: str) -> None:
        """Preview file as image."""
        try:
            content = file.get_content()
            image = self._decode_image(content, ext)

            if image is None or image.isNull():
                self._show_text(f"[Failed to decode image: {file.name}]")
                return

            pixmap = QPixmap.fromImage(image)
            self._current_pixmap = pixmap
            self._update_image_display()
            self._stack.setCurrentWidget(self._image_view)
            logger.debug(
                "Previewed image: %s (%dx%d)", file.name, image.width(), image.height()
            )
        except (DDJDecodeError, DDSDecodeError) as e:
            logger.warning("Image decode error: %s - %s", file.name, e)
            self._show_text(f"[Image decode error: {e}]")
        except Exception as e:
            logger.exception("Image preview failed: %s", file.name)
            self._show_text(f"[Error loading image: {e}]")

    def _decode_image(self, content: bytes, ext: str) -> QImage | None:
        """Decode image bytes to QImage based on extension."""
        if ext == ".ddj":
            # DDJ: strip header, then decode as DDS
            dds_data = decode_ddj(content)
            return decode_dds(dds_data)
        elif ext == ".dds":
            return decode_dds(content)
        else:
            # Standard format - use Qt's built-in decoder
            image = QImage()
            if image.loadFromData(content):
                return image
            return None

    def _update_image_display(self) -> None:
        """Update image display with proper scaling."""
        if self._current_pixmap is None:
            return

        # Get available size
        available_size = self._image_view.size()
        if available_size.width() <= 0 or available_size.height() <= 0:
            # Widget not yet sized, use pixmap as-is
            self._image_view.setPixmap(self._current_pixmap)
            return

        # Scale to fit while maintaining aspect ratio
        scaled = self._current_pixmap.scaled(
            available_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image_view.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        """Handle resize to update image scaling."""
        super().resizeEvent(event)
        if self._current_pixmap is not None:
            self._update_image_display()

    def _looks_like_text(self, content: bytes) -> bool:
        """Check if content appears to be text (no null bytes in first 8KB)."""
        sample = content[:8192]
        return b"\x00" not in sample

    def clear_preview(self) -> None:
        """Clear the preview."""
        self._current_pixmap = None
        self._text_view.clear()
        self._image_view.clear()
        self._stack.setCurrentWidget(self._text_view)

    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        if "." in filename:
            return "." + filename.rsplit(".", 1)[1].lower()
        return ""
