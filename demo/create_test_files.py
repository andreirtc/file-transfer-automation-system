"""
Demo / Test Script — File Transfer Automation System

Creates demo source/destination folders and provides test scenarios:
1. Create a normal small file (should transfer immediately)
2. Simulate a slowly-growing file (should stay PROCESSING)
3. Create multiple test files

Run this script from the project root:
    python demo/create_test_files.py

Or with the venv:
    .venv\Scripts\python.exe demo/create_test_files.py
"""

import os
import sys
import time
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "demo"
SOURCE_DIR = DEMO_DIR / "source"
DEST_DIR = DEMO_DIR / "destination"


def setup_demo_dirs():
    """Create demo source and destination directories."""
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    DEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Demo directories created:")
    print(f"  Source:      {SOURCE_DIR}")
    print(f"  Destination: {DEST_DIR}")
    print()


def create_small_file():
    """Test 1 — Create a small file that should be immediately ready."""
    file_path = SOURCE_DIR / "report.txt"
    file_path.write_text(
        "Quarterly Report\n"
        "================\n"
        "This is a sample report file for testing.\n"
        "It should be detected and transferred quickly.\n"
    )
    print(f"✓ Created small file: {file_path.name} ({file_path.stat().st_size} bytes)")
    print(f"  Expected: DETECTED → READY → TRANSFERRING → VERIFYING → COMPLETED")
    print()


def create_multiple_files():
    """Create several small test files."""
    test_files = {
        "document.pdf": "Fake PDF content for testing purposes. " * 100,
        "image.jpg": "JFIF" + "\x00" * 500 + "fake image data " * 200,
        "spreadsheet.csv": "Name,Value,Date\n" + "item,100,2024-01-01\n" * 50,
        "notes.txt": "Meeting notes\n" + "- Action item\n" * 30,
    }

    for filename, content in test_files.items():
        file_path = SOURCE_DIR / filename
        file_path.write_text(content, encoding="utf-8", errors="replace")
        print(f"✓ Created: {filename} ({file_path.stat().st_size} bytes)")

    print(f"\n  Total: {len(test_files)} files created")
    print()


def simulate_growing_file():
    """
    Test 2 — Simulate a file being downloaded/written over time.

    The file grows in chunks with pauses between writes.
    The transfer system should detect this as PROCESSING and wait.
    """
    file_path = SOURCE_DIR / "large_download.zip"
    chunk_size = 50_000  # 50 KB per chunk
    total_chunks = 20    # Total: ~1 MB
    delay = 1.0          # 1 second between chunks

    print(f"Simulating slowly-growing file: {file_path.name}")
    print(f"  Chunk size: {chunk_size:,} bytes")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Delay between chunks: {delay}s")
    print(f"  Expected final size: ~{chunk_size * total_chunks:,} bytes")
    print()
    print("  The transfer system should keep this file in PROCESSING state")
    print("  until writing stops, then transition to READY.")
    print()

    with open(file_path, "wb") as f:
        for i in range(total_chunks):
            data = bytes([i % 256]) * chunk_size
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            progress = (i + 1) / total_chunks * 100
            size = (i + 1) * chunk_size
            print(f"  Writing chunk {i+1}/{total_chunks} "
                  f"({size:,} bytes, {progress:.0f}%)")
            time.sleep(delay)

    final_size = file_path.stat().st_size
    print(f"\n✓ File writing complete: {file_path.name} ({final_size:,} bytes)")
    print(f"  The system should now transition: PROCESSING → READY → TRANSFERRING")
    print()


def clean_demo():
    """Remove all files from demo directories."""
    for dir_path in [SOURCE_DIR, DEST_DIR]:
        if dir_path.exists():
            for f in dir_path.iterdir():
                if f.is_file() and f.name != ".gitkeep":
                    f.unlink()
                    print(f"  Removed: {f.name}")
    print("✓ Demo directories cleaned")
    print()


def print_menu():
    print("=" * 60)
    print("  File Transfer Automation System — Demo Script")
    print("=" * 60)
    print()
    print("Options:")
    print("  1. Setup demo directories")
    print("  2. Create a small test file (instant ready)")
    print("  3. Create multiple test files")
    print("  4. Simulate a slowly-growing file (takes ~20s)")
    print("  5. Clean demo directories")
    print("  6. Full demo (setup + small files + growing file)")
    print("  0. Exit")
    print()


def main():
    while True:
        print_menu()
        choice = input("Enter choice [0-6]: ").strip()

        if choice == "0":
            print("Goodbye!")
            break
        elif choice == "1":
            setup_demo_dirs()
        elif choice == "2":
            setup_demo_dirs()
            create_small_file()
        elif choice == "3":
            setup_demo_dirs()
            create_multiple_files()
        elif choice == "4":
            setup_demo_dirs()
            simulate_growing_file()
        elif choice == "5":
            clean_demo()
        elif choice == "6":
            setup_demo_dirs()
            create_small_file()
            create_multiple_files()
            print("Now starting the slowly-growing file simulation...")
            print("(You can start the application while this runs)\n")
            simulate_growing_file()
        else:
            print("Invalid choice. Please enter 0-6.\n")

        input("\nPress Enter to continue...")
        print()


if __name__ == "__main__":
    main()
