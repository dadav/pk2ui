"""Service layer for archive comparison operations."""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from PyQt6.QtCore import QObject, pyqtSignal
from pk2api import Pk2Stream, compare_archives, ChangeType, ComparisonResult

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


class DiffType(Enum):
    """Visual diff classification for UI."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"

    @classmethod
    def from_change_type(cls, change_type: ChangeType) -> "DiffType":
        """Convert pk2api ChangeType to DiffType.

        pk2api semantics (comparing source vs target):
        - ADDED = file exists in target but not in source
        - REMOVED = file exists in source but not in target

        We map to our DiffType which uses source-centric naming:
        - ADDED = only in source (pk2api calls this REMOVED)
        - REMOVED = only in target (pk2api calls this ADDED)
        """
        mapping = {
            ChangeType.ADDED: cls.REMOVED,    # pk2api: in target only → our: "Only in Target"
            ChangeType.REMOVED: cls.ADDED,    # pk2api: in source only → our: "Only in Source"
            ChangeType.MODIFIED: cls.MODIFIED,
            ChangeType.UNCHANGED: cls.UNCHANGED,
        }
        return mapping.get(change_type, cls.UNCHANGED)


@dataclass
class ComparisonConfig:
    """Configuration for comparison operation."""

    source_path: str
    source_key: str
    target_path: str
    target_key: str
    compute_hashes: bool = True


@dataclass
class DiffItem:
    """Represents a single diff entry for UI display."""

    path: str
    diff_type: DiffType
    is_folder: bool
    source_size: Optional[int] = None
    target_size: Optional[int] = None
    source_hash: Optional[str] = None
    target_hash: Optional[str] = None


class ComparisonService(QObject):
    """Service layer for archive comparison operations."""

    comparison_finished = pyqtSignal(object)
    copy_finished = pyqtSignal(int, int)
    operation_error = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self._source_stream: Optional[Pk2Stream] = None
        self._target_stream: Optional[Pk2Stream] = None
        self._result: Optional[ComparisonResult] = None
        self._config: Optional[ComparisonConfig] = None

    @property
    def is_open(self) -> bool:
        return self._source_stream is not None and self._target_stream is not None

    @property
    def source_stream(self) -> Optional[Pk2Stream]:
        return self._source_stream

    @property
    def target_stream(self) -> Optional[Pk2Stream]:
        return self._target_stream

    @property
    def result(self) -> Optional[ComparisonResult]:
        return self._result

    def open_archives(self, config: ComparisonConfig) -> bool:
        """Open both source and target archives."""
        logger.info(
            "Opening archives for comparison: %s vs %s",
            config.source_path,
            config.target_path,
        )
        self.close()

        try:
            self._source_stream = Pk2Stream(
                config.source_path, config.source_key, read_only=False
            )
        except Exception as e:
            logger.exception("Failed to open source archive: %s", config.source_path)
            self.operation_error.emit("Source Archive Error", str(e))
            return False

        try:
            self._target_stream = Pk2Stream(
                config.target_path, config.target_key, read_only=False
            )
        except Exception as e:
            logger.exception("Failed to open target archive: %s", config.target_path)
            self._source_stream.close()
            self._source_stream = None
            self.operation_error.emit("Target Archive Error", str(e))
            return False

        self._config = config
        logger.info("Both archives opened successfully")
        return True

    def compare(self) -> Optional[ComparisonResult]:
        """Run comparison using pk2api.compare_archives()."""
        if not self.is_open:
            return None

        logger.info("Running archive comparison")
        try:
            self._result = compare_archives(
                self._source_stream,
                self._target_stream,
                compute_hashes=self._config.compute_hashes if self._config else True,
            )
            logger.info(
                "Comparison complete: %d file changes, %d folder changes",
                len(self._result.file_changes),
                len(self._result.folder_changes),
            )
            self.comparison_finished.emit(self._result)
            return self._result
        except Exception as e:
            logger.exception("Comparison failed")
            self.operation_error.emit("Comparison Error", str(e))
            return None

    def get_diff_items(self) -> list[DiffItem]:
        """Convert ComparisonResult to UI-friendly DiffItem list."""
        if not self._result:
            return []

        items = []

        for folder_change in self._result.folder_changes:
            items.append(
                DiffItem(
                    path=folder_change.path,
                    diff_type=DiffType.from_change_type(folder_change.change_type),
                    is_folder=True,
                )
            )

        for file_change in self._result.file_changes:
            items.append(
                DiffItem(
                    path=file_change.path,
                    diff_type=DiffType.from_change_type(file_change.change_type),
                    is_folder=False,
                    source_size=file_change.source_size,
                    target_size=file_change.target_size,
                    source_hash=getattr(file_change, "source_hash", None),
                    target_hash=getattr(file_change, "target_hash", None),
                )
            )

        return items

    def copy_file(
        self, source_path: str, target_path: Optional[str] = None
    ) -> bool:
        """Copy single file from source to target."""
        if not self.is_open:
            return False

        logger.info("Copying file: %s -> %s", source_path, target_path or source_path)
        try:
            self._target_stream.copy_file_from(
                self._source_stream, source_path, target_path
            )
            return True
        except Exception as e:
            logger.exception("Copy file failed: %s", source_path)
            self.operation_error.emit("Copy Error", str(e))
            return False

    def copy_files(
        self,
        paths: list[str],
        target_base: str = "",
        progress: Optional[ProgressCallback] = None,
    ) -> tuple[int, int]:
        """Copy multiple files from source to target."""
        if not self.is_open:
            return (0, 0)

        logger.info("Copying %d files", len(paths))
        success = 0
        failed = 0

        for i, path in enumerate(paths):
            if progress:
                progress(i, len(paths))
            try:
                target_path = f"{target_base}/{path}" if target_base else None
                self._target_stream.copy_file_from(
                    self._source_stream, path, target_path
                )
                success += 1
            except Exception as e:
                logger.exception("Failed to copy: %s", path)
                failed += 1

        if progress:
            progress(len(paths), len(paths))

        self.copy_finished.emit(success, failed)
        return (success, failed)

    def copy_folder(
        self,
        source_path: str,
        target_path: Optional[str] = None,
        progress: Optional[ProgressCallback] = None,
    ) -> bool:
        """Copy folder from source to target."""
        if not self.is_open:
            return False

        logger.info(
            "Copying folder: %s -> %s", source_path, target_path or source_path
        )
        try:
            self._target_stream.copy_folder_from(
                self._source_stream, source_path, target_path, progress=progress
            )
            return True
        except Exception as e:
            logger.exception("Copy folder failed: %s", source_path)
            self.operation_error.emit("Copy Folder Error", str(e))
            return False

    def close(self) -> None:
        """Close both archive streams."""
        if self._source_stream:
            logger.info("Closing source archive")
            self._source_stream.close()
            self._source_stream = None

        if self._target_stream:
            logger.info("Closing target archive")
            self._target_stream.close()
            self._target_stream = None

        self._result = None
        self._config = None
