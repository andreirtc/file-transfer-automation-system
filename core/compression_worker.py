"""
Helper compression worker executed in an isolated child subprocess.

Running pyminizip in an independent OS process prevents GIL contention
with PySide6's Qt GUI event loop, ensuring 100% smooth UI responsiveness
even during heavy multi-gigabyte compression.
"""

from __future__ import annotations

import json
import os
import sys


def compress_files(
    src_paths: list[str],
    prefixes: list[str],
    zip_path: str,
    password: str | None = None,
    compression_level: int = 4,
) -> bool:
    """Run pyminizip.compress_multiple in the current process with stdout progress reporting."""
    import pyminizip

    pwd = password if (password and len(password) > 0) else None

    def on_progress(count: int):
        try:
            sys.stdout.write(f"PROGRESS:{count}\n")
            sys.stdout.flush()
        except Exception:
            pass

    pyminizip.compress_multiple(
        src_paths,
        prefixes,
        zip_path,
        pwd,
        compression_level,
        on_progress,
    )
    return True


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python -m core.compression_worker <config_json_path>\n")
        sys.exit(1)

    config_path = sys.argv[1]
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        src_paths = data["src_paths"]
        prefixes = data["prefixes"]
        zip_path = data["zip_path"]
        password = data.get("password")
        compression_level = data.get("compression_level", 4)

        compress_files(src_paths, prefixes, zip_path, password, compression_level)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Compression error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
