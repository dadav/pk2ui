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
- **Features:** `features/` → self-contained modules (tree_browser, file_details, text_preview, image_preview, dialogs)

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
- pk2api <= 2 (uses 1.1.0 features when available)
- pyinstaller >= 6.17.0 (dev only)

## pk2api 1.1.0 Feature Usage
The application uses pk2api 1.1.0 features with graceful fallback for older versions:
- **get_stats()**: Used for archive statistics (file count, folder count, sizes) instead of private attribute access
- **original_name/get_original_path()**: Used for case-accurate display in tree and details panel
- **extract_folder/extract_all with progress**: Used for folder extraction with progress callbacks
- **import_from_disk**: Used for bulk folder import
- **glob()**: Available via `ArchiveService.glob()` method for pattern matching
- **compare_archives()**: Used for archive comparison (see Comparison Feature below)
- **copy_file_from/copy_folder_from**: Used for copying files between archives

### Archive Comparison Feature
The `features/comparison/` module provides archive comparison functionality:
- **ComparisonWindow**: Dedicated window for comparing two archives side-by-side
- **ComparisonTreeWidget**: Tree view with diff highlighting (colors + icons)
- **SelectArchivesDialog**: Dialog for selecting source and target archives

**Usage (Tools > Compare Archives...):**
1. Select source and target PK2 archives
2. View differences with visual indicators (green=added, red=removed, yellow=modified)
3. Copy files from source to target via context menu or toolbar

**pk2api comparison module usage:**
```python
from pk2api import compare_archives, ChangeType, ComparisonResult

result = compare_archives(source_stream, target_stream, compute_hashes=True)
for change in result.file_changes:
    if change.change_type == ChangeType.MODIFIED:
        target_stream.copy_file_from(source_stream, change.path)
```

### Filter Panel
The name filter supports glob patterns (`*.txt`, `data*`, `??.xml`). The filter system uses Python's `fnmatch` module for pattern matching when glob characters are detected.

### Image Preview
The `TextPreviewWidget` in `features/text_preview/` supports both text and image preview:
- **Text formats:** .txt, .ini, .xml, .cfg, .log, .json, .csv, .html, .md, .yaml
- **Image formats:** .ddj, .dds, .png, .jpg, .jpeg, .gif, .bmp, .tga, .ico

#### DDJ/DDS Support
The `features/image_preview/` module provides pure Python decoders for Silkroad-specific formats:
- **DDJ:** Joymax container format - strips 20-byte header to expose DDS data
- **DDS:** DirectDraw Surface with DXT1/DXT3/DXT5 (S3TC) block compression support

DDJ Header Structure:
```
Offset  Size  Content
0       9     "JMXVDDJ 1" magic
9       3     Padding (0x30 x3)
12      4     File size - 1 (big-endian)
16      4     Constant (0x03000000)
20      ...   DDS data
```

## Known Issues
See `issues.md` for tracked bugs:
- UI blocks during PK2 file open operations (needs progress indicator)
