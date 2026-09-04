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


CHUNK_SIZE = 1024 * 1024 * 4  # 4 MB chunks


def _stream_write_file(zf, src_path: str, arcname: str, on_bytes) -> None:
    try:
        fsize = os.path.getsize(src_path)
    except OSError:
        fsize = 0

    if fsize == 0:
        with zf.open(arcname, "w") as dest_f:
            pass
        return

    with open(src_path, "rb") as src_f:
        with zf.open(arcname, "w") as dest_f:
            while True:
                chunk = src_f.read(CHUNK_SIZE)
                if not chunk:
                    break
                dest_f.write(chunk)
                on_bytes(len(chunk))


def compress_files(
    src_paths: list[str],
    prefixes: list[str],
    zip_path: str,
    password: str | None = None,
    compression_level: int = 1,
    total_bytes: int = 0,
) -> bool:
    """Run zip compression with stdout progress and native Zip64 support for >4GB archives."""
    pwd = password if (password and len(password) > 0) else None

    # Normalize paths
    norm_srcs = [os.path.normpath(p) for p in src_paths]
    norm_prefixes = [p.replace("\\", "/") if p else "" for p in prefixes]

    # Calculate total bytes upfront if not precalculated
    if not total_bytes or total_bytes <= 0:
        total_bytes = 0
        for p in norm_srcs:
            try:
                if os.path.exists(p):
                    total_bytes += os.path.getsize(p)
            except OSError:
                pass
    if total_bytes <= 0:
        total_bytes = 1

    # Immediately flush 0-byte initial progress so the UI progress bar displays instantly
    try:
        sys.stdout.write(f"PROGRESS_BYTES:0:{total_bytes}\n")
        sys.stdout.flush()
    except Exception:
        pass

    current_bytes = 0

    def on_bytes_written(n: int):
        nonlocal current_bytes
        current_bytes += n
        try:
            sys.stdout.write(f"PROGRESS_BYTES:{current_bytes}:{total_bytes}\n")
            sys.stdout.flush()
        except Exception:
            pass

    def on_progress(count: int):
        try:
            sys.stdout.write(f"PROGRESS:{count}\n")
            sys.stdout.flush()
        except Exception:
            pass

    # If no password is set, standard zipfile with allowZip64=True guarantees
    # seamless support for large datasets (> 4 GB, such as 7.8 GB folders)
    # without 32-bit header overflow or Windows Explorer corruption.
    if not pwd:
        import zipfile
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level, allowZip64=True) as zf:
            for i, sp in enumerate(norm_srcs):
                if not os.path.exists(sp):
                    continue
                prefix = norm_prefixes[i] if i < len(norm_prefixes) else ""
                arcname = os.path.join(prefix, os.path.basename(sp)).replace("\\", "/") if prefix else os.path.basename(sp)
                _stream_write_file(zf, sp, arcname, on_bytes_written)
                on_progress(i + 1)
        return True

    # Try pyzipper AESZipFile first for high-speed Zip64 encryption
    try:
        import pyzipper
        pwd_bytes = pwd.encode("utf-8") if isinstance(pwd, str) else pwd
        with pyzipper.AESZipFile(
            zip_path,
            "w",
            compression=pyzipper.ZIP_DEFLATED,
            compresslevel=compression_level,
            encryption=pyzipper.WZ_AES,
            allowZip64=True,
        ) as zf:
            zf.setpassword(pwd_bytes)
            for i, sp in enumerate(norm_srcs):
                if not os.path.exists(sp):
                    continue
                prefix = norm_prefixes[i] if i < len(norm_prefixes) else ""
                arcname = os.path.join(prefix, os.path.basename(sp)).replace("\\", "/") if prefix else os.path.basename(sp)
                _stream_write_file(zf, sp, arcname, on_bytes_written)
                on_progress(i + 1)
        return True
    except Exception as e:
        sys.stderr.write(f"pyzipper warning: {e}, falling back to pyminizip\n")

    try:
        import pyminizip
        pyminizip.compress_multiple(
            norm_srcs,
            norm_prefixes,
            zip_path,
            pwd,
            compression_level,
            on_progress,
        )
        return True
    except Exception as e:
        sys.stderr.write(f"pyminizip warning: {e}, falling back to zipfile\n")
        import zipfile
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=compression_level, allowZip64=True) as zf:
            for i, sp in enumerate(norm_srcs):
                if not os.path.exists(sp):
                    continue
                prefix = norm_prefixes[i] if i < len(norm_prefixes) else ""
                arcname = os.path.join(prefix, os.path.basename(sp)).replace("\\", "/") if prefix else os.path.basename(sp)
                _stream_write_file(zf, sp, arcname, on_bytes_written)
                on_progress(i + 1)
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
        total_bytes = data.get("total_bytes", 0)

        compress_files(src_paths, prefixes, zip_path, password, compression_level, total_bytes)
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Compression error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
