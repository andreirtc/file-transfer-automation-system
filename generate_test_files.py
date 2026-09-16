"""
Generates dummy Oracle dump files (.dmp) with exact timestamps to test:
1. Standard evening file (Sept 15, 23:15)
2. 'Tumatawid' midnight crossover file (Sept 16, 02:30 -> belongs to Sept 15 cycle!)
3. Next day file (Sept 16, 23:45 -> belongs to Sept 16 cycle)
"""

import os
from datetime import datetime
from pathlib import Path

def setup_demo_environment():
    root = Path(__file__).resolve().parent
    source_dir = root / "demo_oracle_test" / "source"
    dest_dir = root / "demo_oracle_test" / "destination"

    source_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 1. File 1: September 15, 2026 23:15:00 (Standard evening backup)
    f1 = source_dir / "ORCL_TFS_20260915_2315.dmp"
    f1.write_bytes(b"[ORACLE DUMP V19.3 HEADER]\nDATA_BLOCK_SEPT_15_EVENING\n" + b"\x00" * (1024 * 512))
    dt1 = datetime(2026, 9, 15, 23, 15, 0).timestamp()
    os.utime(f1, (dt1, dt1))
    print(f"Created: {f1.name} (mtime: 2026-09-15 23:15:00)")

    # 2. File 2: September 16, 2026 02:30:00 ('Tumatawid' crossover file belonging to Sept 15 batch!)
    f2 = source_dir / "ORCL_TFS_20260916_0230.dmp"
    f2.write_bytes(b"[ORACLE DUMP V19.3 HEADER]\nDATA_BLOCK_SEPT_15_OVERNIGHT_CROSSOVER\n" + b"\x00" * (1024 * 512))
    dt2 = datetime(2026, 9, 16, 2, 30, 0).timestamp()
    os.utime(f2, (dt2, dt2))
    print(f"Created: {f2.name} (mtime: 2026-09-16 02:30:00 -> Tumatawid to Sept 15)")

    # 3. File 3: September 16, 2026 23:45:00 (Next day's operational cycle)
    f3 = source_dir / "ORCL_TFS_20260916_2345.dmp"
    f3.write_bytes(b"[ORACLE DUMP V19.3 HEADER]\nDATA_BLOCK_SEPT_16_EVENING\n" + b"\x00" * (1024 * 512))
    dt3 = datetime(2026, 9, 16, 23, 45, 0).timestamp()
    os.utime(f3, (dt3, dt3))
    print(f"Created: {f3.name} (mtime: 2026-09-16 23:45:00 -> Sept 16 cycle)")

    print("\nDummy test files ready in demo_oracle_test/source.")
    print("Destination folder ready in demo_oracle_test/destination.")

if __name__ == "__main__":
    setup_demo_environment()
