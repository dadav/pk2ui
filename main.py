"""PK2UI - PyQt6 PK2 Archive Editor."""

import sys

from PyQt6.QtWidgets import QApplication

from app.logging_config import setup_logging
from app.main_window import MainWindow
from app.version import get_version


def main() -> int:
    """Application entry point."""
    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"pk2ui {get_version()}")
        return 0

    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("PK2 Editor")
    app.setApplicationVersion(get_version())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
