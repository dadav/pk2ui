"""Background worker threads for comparison and copy operations."""

import logging

from PyQt6.QtCore import QThread, pyqtSignal
from pk2api import Pk2Stream, compare_archives, ComparisonResult

from .comparison_service import ComparisonConfig

logger = logging.getLogger(__name__)


class CompareWorker(QThread):
    """Background worker for archive comparison."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        config: ComparisonConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._source_stream: Pk2Stream | None = None
        self._target_stream: Pk2Stream | None = None

    @property
    def source_stream(self) -> Pk2Stream | None:
        return self._source_stream

    @property
    def target_stream(self) -> Pk2Stream | None:
        return self._target_stream

    def run(self) -> None:
        """Execute comparison in background thread."""
        try:
            logger.info(
                "CompareWorker: opening %s and %s",
                self._config.source_path,
                self._config.target_path,
            )

            self._source_stream = Pk2Stream(
                self._config.source_path,
                self._config.source_key,
                read_only=True,
            )

            self._target_stream = Pk2Stream(
                self._config.target_path,
                self._config.target_key,
                read_only=False,
            )

            logger.info("CompareWorker: running comparison")
            result = compare_archives(
                self._source_stream,
                self._target_stream,
                compute_hashes=self._config.compute_hashes,
                include_unchanged=True,
            )

            logger.info(
                "CompareWorker: comparison complete, %d file changes",
                len(result.file_changes),
            )
            self.finished.emit(result)

        except Exception as e:
            logger.exception("CompareWorker: comparison failed")
            self.error.emit(str(e))
            self._cleanup()

    def _cleanup(self) -> None:
        """Close streams on error."""
        if self._source_stream:
            self._source_stream.close()
            self._source_stream = None
        if self._target_stream:
            self._target_stream.close()
            self._target_stream = None


class CopyWorker(QThread):
    """Background worker for copy operations."""

    finished = pyqtSignal(int, int)
    progress = pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(
        self,
        source: Pk2Stream,
        target: Pk2Stream,
        items: list[tuple[str, bool]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._target = target
        self._items = items

    def run(self) -> None:
        """Execute copy operations in background thread."""
        success = 0
        failed = 0
        total = len(self._items)

        logger.info("CopyWorker: copying %d items", total)

        for i, (path, is_folder) in enumerate(self._items):
            self.progress.emit(i, total)
            try:
                if is_folder:
                    self._target.copy_folder_from(self._source, path)
                else:
                    self._target.copy_file_from(self._source, path)
                success += 1
            except Exception as e:
                logger.exception("CopyWorker: failed to copy %s", path)
                failed += 1

        self.progress.emit(total, total)
        logger.info("CopyWorker: complete, %d success, %d failed", success, failed)
        self.finished.emit(success, failed)
