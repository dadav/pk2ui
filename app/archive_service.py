"""Service layer for PK2 archive operations."""

import logging
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from pk2api import Pk2AuthenticationError, Pk2File, Pk2Folder, Pk2Stream

# Type alias for progress callback
ProgressCallback = Callable[[int, int], None]

logger = logging.getLogger(__name__)


class ArchiveService(QObject):
    """Manages a single PK2 archive instance."""

    # Signals
    archive_opened = pyqtSignal(str)  # Emits archive path
    archive_closed = pyqtSignal()
    archive_modified = pyqtSignal()  # Emits when contents change
    operation_error = pyqtSignal(str, str)  # title, message

    def __init__(self) -> None:
        super().__init__()
        self._stream: Optional[Pk2Stream] = None
        self._path: Optional[Path] = None

    @property
    def is_open(self) -> bool:
        return self._stream is not None

    @property
    def archive_path(self) -> Optional[Path]:
        return self._path

    @property
    def root_folder(self) -> Optional[Pk2Folder]:
        if self._stream:
            return self._stream.get_folder("")
        return None

    def open_archive(
        self,
        path: str,
        key: str = "169841",
        progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Open a PK2 archive. Returns True on success.

        Args:
            path: Path to the PK2 file
            key: Blowfish encryption key
            progress: Optional callback(blocks_loaded, estimated_total) for progress
        """
        logger.info("Opening archive: %s", path)
        self.close_archive()
        try:
            self._stream = Pk2Stream(path, key, read_only=False, progress=progress)
            self._path = Path(path)
            file_count = self.get_file_count()
            logger.info("Archive opened successfully: %d files", file_count)
            self.archive_opened.emit(path)
            return True
        except Pk2AuthenticationError:
            logger.error("Invalid encryption key for: %s", path)
            self.operation_error.emit(
                "Authentication Error", "Invalid encryption key"
            )
            return False
        except Exception as e:
            logger.exception("Failed to open archive: %s", path)
            self.operation_error.emit("Open Error", str(e))
            return False

    def close_archive(self) -> None:
        """Close the current archive."""
        if self._stream:
            logger.info("Closing archive: %s", self._path)
            self._stream.close()
            self._stream = None
            self._path = None
            self.archive_closed.emit()

    def get_file(self, path: str) -> Optional[Pk2File]:
        """Get a file by path."""
        if not self._stream:
            return None
        return self._stream.get_file(path)

    def get_folder(self, path: str) -> Optional[Pk2Folder]:
        """Get a folder by path."""
        if not self._stream:
            return None
        return self._stream.get_folder(path)

    def extract_file(self, pk2_path: str, dest_path: str) -> bool:
        """Extract a file to disk."""
        logger.info("Extracting: %s -> %s", pk2_path, dest_path)
        file = self.get_file(pk2_path)
        if not file:
            self.operation_error.emit("Extract Error", f"File not found: {pk2_path}")
            return False
        try:
            content = file.get_content()
            Path(dest_path).write_bytes(content)
            logger.info("Extracted %d bytes", len(content))
            return True
        except Exception as e:
            logger.exception("Extract failed: %s", pk2_path)
            self.operation_error.emit("Extract Error", str(e))
            return False

    def extract_folder(
        self,
        pk2_path: str,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Extract a folder and all contents to disk.

        Uses pk2api 1.1.0's extract_folder with progress callback when available.
        """
        logger.info("Extracting folder: %s -> %s", pk2_path, dest_path)
        if not self._stream:
            return False
        try:
            # Use pk2api 1.1.0 extract_folder method with progress callback
            self._stream.extract_folder(pk2_path, dest_path, progress=progress)
            logger.info("Folder extraction complete: %s", pk2_path)
            return True
        except AttributeError:
            # Fallback to manual extraction if extract_folder not available
            logger.info("Falling back to manual folder extraction")
            folder = self.get_folder(pk2_path)
            if not folder:
                self.operation_error.emit(
                    "Extract Error", f"Folder not found: {pk2_path}"
                )
                return False
            dest = Path(dest_path)
            dest.mkdir(parents=True, exist_ok=True)
            return self._extract_folder_recursive(folder, dest, pk2_path)
        except Exception as e:
            logger.exception("Extract folder failed: %s", pk2_path)
            self.operation_error.emit("Extract Error", str(e))
            return False

    def extract_all(
        self,
        dest_path: str,
        progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Extract entire archive to disk.

        Uses pk2api 1.1.0's extract_all with progress callback.
        """
        logger.info("Extracting entire archive to: %s", dest_path)
        if not self._stream:
            return False
        try:
            self._stream.extract_all(dest_path, progress=progress)
            logger.info("Full archive extraction complete")
            return True
        except Exception as e:
            logger.exception("Extract all failed")
            self.operation_error.emit("Extract Error", str(e))
            return False

    def _extract_folder_recursive(
        self, folder: Pk2Folder, dest: Path, pk2_path: str
    ) -> bool:
        """Recursively extract folder contents (fallback for older pk2api)."""
        # Extract files
        for name, file in folder.files.items():
            file_dest = dest / name
            content = file.get_content()
            file_dest.write_bytes(content)

        # Extract subfolders
        for name, subfolder in folder.folders.items():
            subfolder_dest = dest / name
            subfolder_dest.mkdir(exist_ok=True)
            subfolder_pk2_path = f"{pk2_path}/{name}" if pk2_path else name
            self._extract_folder_recursive(subfolder, subfolder_dest, subfolder_pk2_path)

        return True

    def import_file(self, disk_path: str, pk2_path: str) -> bool:
        """Import a file from disk into the archive."""
        logger.info("Importing: %s -> %s", disk_path, pk2_path)
        if not self._stream:
            return False
        try:
            content = Path(disk_path).read_bytes()
            success = self._stream.add_file(pk2_path, content)
            if success:
                logger.info("Imported %d bytes", len(content))
                self.archive_modified.emit()
            else:
                self.operation_error.emit("Import Error", "Failed to add file")
            return success
        except Exception as e:
            logger.exception("Import failed: %s", disk_path)
            self.operation_error.emit("Import Error", str(e))
            return False

    def import_folder(self, disk_path: str, pk2_path: str) -> tuple[int, int]:
        """Import a folder and all contents from disk into the archive.

        Uses pk2api 1.1.0's import_from_disk method when available.
        Returns (imported_count, failed_count).
        """
        logger.info("Importing folder: %s -> %s", disk_path, pk2_path)
        if not self._stream:
            return (0, 0)
        try:
            # Use pk2api 1.1.0 import_from_disk method
            self._stream.import_from_disk(disk_path, pk2_path)
            # Count imported files from disk source
            imported = self._count_disk_files(Path(disk_path))
            self.archive_modified.emit()
            logger.info("Folder import complete via import_from_disk")
            return (imported, 0)
        except AttributeError:
            # Fallback to manual import if import_from_disk not available
            logger.info("Falling back to manual folder import")
            imported, failed = self._import_folder_recursive(Path(disk_path), pk2_path)
            if imported > 0:
                self.archive_modified.emit()
            logger.info("Folder import complete: %d imported, %d failed", imported, failed)
            return (imported, failed)
        except Exception as e:
            logger.exception("Import folder failed: %s", disk_path)
            self.operation_error.emit("Import Folder Error", str(e))
            return (0, 1)

    def _count_folder_files(self, folder: Pk2Folder) -> int:
        """Count files in a folder recursively."""
        count = len(folder.files)
        for subfolder in folder.folders.values():
            count += self._count_folder_files(subfolder)
        return count

    def _count_disk_files(self, path: Path) -> int:
        """Count files in a disk folder recursively."""
        count = 0
        for item in path.iterdir():
            if item.is_file():
                count += 1
            elif item.is_dir():
                count += self._count_disk_files(item)
        return count

    def _import_folder_recursive(self, disk_path: Path, pk2_path: str) -> tuple[int, int]:
        """Recursively import folder contents (fallback for older pk2api)."""
        imported = 0
        failed = 0

        for item in disk_path.iterdir():
            if pk2_path:
                item_pk2_path = f"{pk2_path}/{item.name}"
            else:
                item_pk2_path = item.name

            if item.is_file():
                try:
                    content = item.read_bytes()
                    if self._stream.add_file(item_pk2_path, content):
                        imported += 1
                    else:
                        failed += 1
                except Exception:
                    logger.exception("Failed to import: %s", item)
                    failed += 1
            elif item.is_dir():
                sub_imported, sub_failed = self._import_folder_recursive(item, item_pk2_path)
                imported += sub_imported
                failed += sub_failed

        return (imported, failed)

    def create_folder(self, pk2_path: str) -> bool:
        """Create a new folder in the archive."""
        logger.info("Creating folder: %s", pk2_path)
        if not self._stream:
            return False
        try:
            success = self._stream.add_folder(pk2_path)
            if success:
                self.archive_modified.emit()
            else:
                self.operation_error.emit(
                    "Create Folder Error", "Folder already exists or invalid path"
                )
            return success
        except Exception as e:
            logger.exception("Create folder failed: %s", pk2_path)
            self.operation_error.emit("Create Folder Error", str(e))
            return False

    def delete_file(self, pk2_path: str) -> bool:
        """Delete a file from the archive."""
        logger.info("Deleting file: %s", pk2_path)
        if not self._stream:
            return False
        try:
            success = self._stream.remove_file(pk2_path)
            if success:
                self.archive_modified.emit()
            return success
        except Exception as e:
            logger.exception("Delete failed: %s", pk2_path)
            self.operation_error.emit("Delete Error", str(e))
            return False

    def delete_folder(self, pk2_path: str) -> bool:
        """Delete a folder and its contents."""
        logger.info("Deleting folder: %s", pk2_path)
        if not self._stream:
            return False
        try:
            success = self._stream.remove_folder(pk2_path)
            if success:
                self.archive_modified.emit()
            return success
        except Exception as e:
            logger.exception("Delete failed: %s", pk2_path)
            self.operation_error.emit("Delete Error", str(e))
            return False

    def get_stats(self) -> dict:
        """Get archive statistics using pk2api 1.1.0 get_stats().

        Returns dict with: files, folders, total_size, disk_used
        """
        if not self._stream:
            return {"files": 0, "folders": 0, "total_size": 0, "disk_used": 0}
        return self._stream.get_stats()

    def get_file_count(self) -> int:
        """Get total file count in archive."""
        return self.get_stats().get("files", 0)

    def glob(self, pattern: str) -> list[Pk2File]:
        """Find files matching a glob pattern.

        Uses pk2api 1.1.0's glob method for pattern matching.
        Supports patterns like "**/*.txt", "data/*.xml", etc.
        """
        if not self._stream:
            return []
        try:
            return self._stream.glob(pattern)
        except AttributeError:
            logger.warning("glob() not available in this pk2api version")
            return []

    def iter_files(self) -> list[Pk2File]:
        """Iterate over all files in the archive.

        Uses pk2api 1.1.0's iter_files method.
        """
        if not self._stream:
            return []
        try:
            return list(self._stream.iter_files())
        except AttributeError:
            logger.warning("iter_files() not available in this pk2api version")
            return []
