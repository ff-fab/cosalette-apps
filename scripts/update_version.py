#!/usr/bin/env python
"""Script to regenerate version file from git tags using setuptools_scm."""

from pathlib import Path


def main() -> int:
    try:
        import setuptools_scm
    except ImportError:
        print("setuptools_scm not found. Install with: uv sync --group dev")
        return 1

    # Use absolute path for workspace root
    workspace_root = Path("/workspace")
    ver = setuptools_scm.get_version(root=workspace_root, fallback_version="0.0.0")
    version_file = (
        workspace_root / "packages" / "src" / "cosalette_apps" / "_version.py"
    )
    version_file.write_text(f'__version__: str = "{ver}"\n')
    print(f"Updated {version_file} with version: {ver}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
