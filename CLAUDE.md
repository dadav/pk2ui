# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

PK2UI is a PyQt6-based GUI editor for Silkroad Online PK2 archive files. It enables browsing, extracting, importing, and modifying files within PK2 archives using the `pk2api` library.

## Commands

```bash
# Run the application
uv run main.py

# Build standalone executable (Linux)
uv run pyinstaller --onefile --noconsole --name pk2ui \
  --add-data "pyproject.toml:." \
  --hidden-import pk2api --hidden-import PyQt6 \
  --hidden-import PyQt6.QtCore --hidden-import PyQt6.QtWidgets \
  --hidden-import PyQt6.QtGui main.py

# Build standalone executable (Windows - use semicolon instead of colon)
pyinstaller --onefile --noconsole --name pk2ui \
  --add-data "pyproject.toml;." \
  --hidden-import pk2api --hidden-import PyQt6 \
  --hidden-import PyQt6.QtCore --hidden-import PyQt6.QtWidgets \
  --hidden-import PyQt6.QtGui main.py

# Run built executable
./dist/pk2ui
```

## Architecture

### Layered Structure
- **Entry point:** `main.py` → sets up logging, creates QApplication and MainWindow
- **Service layer:** `app/archive_service.py` → encapsulates all pk2api operations, emits signals on state changes
- **UI layer:** `app/main_window.py` → main window, menus, toolbar, splitter layout
- **Features:** `features/` → self-contained modules (tree_browser, file_details, text_preview, dialogs)

### Signal-Based Communication
All components communicate via PyQt6 signals rather than direct method calls:
- `ArchiveService` emits: `archive_opened`, `archive_closed`, `archive_modified`, `operation_error`
- `Pk2TreeWidget` emits: `file_selected`, `folder_selected`, `extract_requested`, `delete_requested`, `import_requested`
- `FilterPanel` emits: `filters_changed`

MainWindow connects these signals to handler methods that coordinate between components.

### Adding New Features
1. Create a new module under `features/` with its own subdirectory
2. Define signals for user actions and state changes
3. Connect signals in MainWindow rather than calling methods directly
4. For archive operations, extend `ArchiveService` with new methods

### Filter System
`FilterCriteria` dataclass in `features/tree_browser/filter_panel.py` defines filter state. Tree widget applies filters recursively during `_populate_tree()`.

## Dependencies
- PyQt6 >= 6.5
- pk2api <= 2
- pyinstaller >= 6.17.0 (dev only)

## Known Issues
See `issues.md` for tracked bugs:
- Imported files show uppercase in listview when replacing existing
- UI blocks during PK2 file open operations (needs progress indicator)
