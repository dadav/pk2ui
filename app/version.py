"""Version information from pyproject.toml."""

import sys
from pathlib import Path

_VERSION = "unknown"


def _load_version() -> str:
    """Load version from pyproject.toml."""
    # When running from PyInstaller bundle
    if getattr(sys, "frozen", False):
        base_path = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base_path = Path(__file__).parent.parent

    pyproject_path = base_path / "pyproject.toml"

    if pyproject_path.exists():
        content = pyproject_path.read_text()
        for line in content.splitlines():
            if line.startswith("version"):
                # Parse: version = "0.1.0"
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    return "unknown"


_VERSION = _load_version()


def get_version() -> str:
    """Get the application version."""
    return _VERSION
