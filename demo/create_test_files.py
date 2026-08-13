"""
Demo / Test Script — File Transfer Automation System

Creates demo source/destination folders and provides test scenarios:
1. Create a normal small file (should transfer immediately)
2. Simulate a slowly-growing file (should stay PROCESSING)
3. Create multiple test files

Run this script from the project root:
    python demo/create_test_files.py

Or with the venv:
    .venv\\Scripts\\python.exe demo/create_test_files.py
"""

import os
import sys
import time
from pathlib import Path

try:
    import msvcrt
except ImportError:
    msvcrt = None


# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = PROJECT_ROOT / "demo"
DEFAULT_SOURCE_DIR = DEMO_DIR / "source"
DEST_DIR = DEMO_DIR / "destination"

# Active source dir (can be overridden)
SOURCE_DIR = DEFAULT_SOURCE_DIR


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

def simulate_locked_file():
    """
    Test 5 — Simulate an OS-level exclusive file lock.
    Uses msvcrt to lock the file for 15 seconds.
    """
    if msvcrt is None:
        print("This test requires Windows (msvcrt module). Skipping.")
        return
        
    file_path = SOURCE_DIR / "locked_file.dat"
    print(f"Simulating OS-locked file: {file_path.name}")
    print("  Creating file and placing exclusive lock...")
    
    with open(file_path, "wb") as f:
        # Lock the file exclusively
        # msvcrt.LK_NBLCK = 2 (Non-blocking lock)
        # We'll just use a blocking lock since we own it, or lock the first byte
        f.write(b"Initial data for locked file.")
        f.flush()
        
        # Lock 100 bytes starting at position 0 using a blocking lock
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 100)
        except PermissionError as e:
            print(f"  ⚠️ Unable to acquire lock: {e}")
            return
        
        print("  ✓ File locked! It should appear as PROCESSING in the app.")
        print("  Holding lock for 15 seconds...")
        for i in range(15, 0, -1):
            print(f"  Releasing in {i}s...", end="\r")
            time.sleep(1)
        
        print("  Releasing lock now...      ")
        # Unlock the bytes before closing the file
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 100)
        except PermissionError as e:
            print(f"  ⚠️ Unable to release lock: {e}")
        
        print(f"✓ Lock released: {file_path.name}")
        print("  The system should now process the file normally.")
        print()

def print_demo_instructions():
    """Print instructions for demoing the new features."""
    print("=" * 60)
    print("  DEMO INSTRUCTIONS")
    print("=" * 60)
    print("1. Transfer Windows (Scheduling)")
    print("   - Edit a job and check 'Transfer during specific time window'")
    print("   - Set the window to start LATER than the current time")
    print("   - Add a file. It should enter 'WAITING_FOR_WINDOW'")
    print("   - You can right-click the file in the table to 'Force Start'")
    print()
    print("2. Timestamped Folders & Multi-Job")
    print("   - Notice the dropdown in the Dashboard to switch jobs")
    print("   - After a transfer, check the Destination folder to see")
    print("     the timestamped subfolders.")
    print("=" * 60)
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
    print("  5. Simulate an OS-locked file (tests PermissionError fix, 15s)")
    print("  6. Clean demo directories")
    print("  7. Full demo (setup + small + growing + locked)")
    print("  8. Show instructions for new features")
    print("  9. Change Target Source Directory (For Network Testing)")
    print("  0. Exit")
    print()
    print(f"  Current Target Source: {SOURCE_DIR}")
    print()


def main():
    global SOURCE_DIR
    while True:
        print_menu()
        choice = input("Enter choice [0-9]: ").strip()

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
            setup_demo_dirs()
            simulate_locked_file()
        elif choice == "6":
            clean_demo()
        elif choice == "7":
            setup_demo_dirs()
            create_small_file()
            create_multiple_files()
            print("Now starting the slowly-growing file simulation...")
            simulate_growing_file()
            print("Now starting the exclusively locked file simulation...")
            simulate_locked_file()
        elif choice == "8":
            print_demo_instructions()
        elif choice == "9":
            new_dir = input(r"Enter new path (e.g., \\LAPTOP\Share) or press enter for default: ").strip()
            if new_dir:
                SOURCE_DIR = Path(new_dir)
            else:
                SOURCE_DIR = DEFAULT_SOURCE_DIR
            print(f"Target Source Directory updated to: {SOURCE_DIR}")
        else:
            print("Invalid choice. Please enter 0-9.\n")

        input("\nPress Enter to continue...")
        print()


if __name__ == "__main__":
    main()
