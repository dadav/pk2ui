"""PK2UI - PyQt6 PK2 Archive Editor."""

import sys

from PyQt6.QtWidgets import QApplication

from app.logging_config import setup_logging
from app.main_window import MainWindow


def main() -> int:
    """Application entry point."""
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("PK2 Editor")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
