"""
Enterprise Administrator Documentation & Technical Reference Interface.

Provides an interactive, multi-section documentation viewer directly within
the application for IT administrators to inspect system operations, user guides,
status lifecycles, transfer protocols, archiving standards, network guidelines,
and comprehensive troubleshooting procedures.
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QTextBrowser,
    QSplitter,
)
from qfluentwidgets import (
    TitleLabel,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    ListWidget,
    ScrollArea,
    FluentIcon,
    SimpleCardWidget,
)


class DocsPageWidget(QWidget):
    """
    Dedicated in-app Enterprise Administrator Documentation & Handover Manual.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DocumentationInterface")
        self._setup_ui()
        self._load_sections()
        # Default to first section
        self._list_widget.setCurrentRow(0)

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(16)

        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)
        self._title = TitleLabel("System Documentation & IT Administrator Manual", self)
        self._subtitle = BodyLabel(
            "Complete operational guide, status lifecycles, transfer protocols, archiving specifications, and IT troubleshooting handbook.",
            self,
        )
        self._subtitle.setStyleSheet("color: #616161; font-size: 13px;")
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._subtitle)
        root_layout.addLayout(header_layout)

        # Splitter Layout (Left: Navigation List, Right: Content Viewer)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #E2E8F0;
            }
        """)

        # Left Nav Panel
        left_card = SimpleCardWidget(self)
        left_card.setStyleSheet("""
            SimpleCardWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(12, 14, 12, 14)
        left_layout.setSpacing(8)

        nav_header = SubtitleLabel("Manual Sections", left_card)
        nav_header.setStyleSheet("font-size: 14px; font-weight: 600; color: #1E293B;")
        left_layout.addWidget(nav_header)

        self._list_widget = ListWidget(left_card)
        self._list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self._list_widget.setStyleSheet("""
            ListWidget {
                background: transparent;
                border: none;
                font-size: 13px;
                color: #334155;
            }
            ListWidget::item {
                padding: 10px 12px;
                border-radius: 6px;
                margin-bottom: 3px;
            }
            ListWidget::item:hover {
                background-color: #F1F5F9;
                color: #0F172A;
            }
            ListWidget::item:selected {
                background-color: #EFF6FF;
                color: #1D4ED8;
                font-weight: 600;
                border-left: 3px solid #2563EB;
            }
        """)
        self._list_widget.currentRowChanged.connect(self._on_section_selected)
        left_layout.addWidget(self._list_widget)

        left_card.setMinimumWidth(260)
        left_card.setMaximumWidth(320)
        splitter.addWidget(left_card)

        # Right Content Panel
        right_card = SimpleCardWidget(self)
        right_card.setStyleSheet("""
            SimpleCardWidget {
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-radius: 8px;
            }
        """)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(24, 20, 24, 20)
        right_layout.setSpacing(10)

        self._content_browser = QTextBrowser(right_card)
        self._content_browser.setOpenExternalLinks(True)
        self._content_browser.setFrameShape(QFrame.Shape.NoFrame)
        self._content_browser.setStyleSheet("""
            QTextBrowser {
                background: transparent;
                border: none;
            }
        """)
        right_layout.addWidget(self._content_browser)

        splitter.addWidget(right_card)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root_layout.addWidget(splitter, stretch=1)

    def _load_sections(self):
        self._sections = [
            ("1. System Overview & Architecture", self._doc_overview()),
            ("2. Admin User Guide (Step-by-Step)", self._doc_user_guide()),
            ("3. Status & Lifecycle Reference Guide", self._doc_statuses()),
            ("4. File Transfer Engine & Safe Copy", self._doc_transfer_engine()),
            ("5. Archiving, Encryption & Passwords", self._doc_compression()),
            ("6. File Safety & In-Use Protection", self._doc_safety_locks()),
            ("7. Network Shares (SMB / UNC) Guide", self._doc_network_shares()),
            ("8. Source File Cleanup & Retention", self._doc_cleanup()),
            ("9. IT Troubleshooting & Practical FAQ", self._doc_troubleshooting()),
            ("10. Admin Verification & Testing Guide", self._doc_testing_guide()),
            ("11. Corporate Daily Backup Report Guide", self._doc_daily_report()),
        ]

        for title, _ in self._sections:
            self._list_widget.addItem(title)

    def _on_section_selected(self, index: int):
        if 0 <= index < len(self._sections):
            _, html = self._sections[index]
            self._content_browser.setHtml(self._wrap_html(html))

    def _wrap_html(self, content: str) -> str:
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Arial, sans-serif;
                    font-size: 13px;
                    line-height: 1.65;
                    color: #1E293B;
                    padding-right: 12px;
                }}
                h1 {{
                    font-size: 18px;
                    font-weight: 700;
                    color: #0F172A;
                    border-bottom: 2px solid #E2E8F0;
                    padding-bottom: 8px;
                    margin-top: 0;
                    margin-bottom: 14px;
                }}
                h2 {{
                    font-size: 15px;
                    font-weight: 600;
                    color: #0F172A;
                    border-bottom: 1px solid #F1F5F9;
                    padding-bottom: 4px;
                    margin-top: 22px;
                    margin-bottom: 8px;
                }}
                h3 {{
                    font-size: 13px;
                    font-weight: 600;
                    color: #0F172A;
                    margin-top: 16px;
                    margin-bottom: 6px;
                }}
                p {{
                    margin-top: 0;
                    margin-bottom: 10px;
                }}
                ul, ol {{
                    margin-top: 4px;
                    margin-bottom: 12px;
                    padding-left: 22px;
                }}
                li {{
                    margin-bottom: 5px;
                }}
                code {{
                    background-color: #F1F5F9;
                    color: #0F172A;
                    padding: 2px 6px;
                    border-radius: 4px;
                    font-family: Consolas, 'Cascadia Code', monospace;
                    font-size: 12px;
                    border: 1px solid #E2E8F0;
                }}
                pre {{
                    background-color: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 6px;
                    padding: 12px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                    line-height: 1.5;
                    overflow-x: auto;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin-top: 10px;
                    margin-bottom: 16px;
                    font-size: 12px;
                }}
                th, td {{
                    border: 1px solid #E2E8F0;
                    padding: 8px 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #F8FAFC;
                    color: #334155;
                    font-weight: 600;
                }}
                .callout-info {{
                    background-color: #EFF6FF;
                    border-left: 4px solid #3B82F6;
                    padding: 12px 14px;
                    border-radius: 4px;
                    margin: 12px 0;
                    color: #1E40AF;
                }}
                .callout-warning {{
                    background-color: #FFFBEB;
                    border-left: 4px solid #F59E0B;
                    padding: 12px 14px;
                    border-radius: 4px;
                    margin: 12px 0;
                    color: #92400E;
                }}
                .callout-success {{
                    background-color: #F0FDF4;
                    border-left: 4px solid #10B981;
                    padding: 12px 14px;
                    border-radius: 4px;
                    margin: 12px 0;
                    color: #065F46;
                }}
                .callout-danger {{
                    background-color: #FEF2F2;
                    border-left: 4px solid #EF4444;
                    padding: 12px 14px;
                    border-radius: 4px;
                    margin: 12px 0;
                    color: #991B1B;
                }}
                .badge {{
                    display: inline-block;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: 600;
                }}
            </style>
        </head>
        <body>
            {content}
        </body>
        </html>
        """

    def _doc_overview(self) -> str:
        return """
        <h1>1. System Overview & Architecture</h1>
        <p>The <b>File Transfer Automation System</b> is a mission-critical Windows desktop application engineered for enterprise environments to automate secure, reliable, one-way file synchronization between local folders and destination network shares.</p>

        <div class="callout-info">
            <b>Purpose of the System:</b> Eliminates manual file copying across branches and departments. It ensures files are 100% finished being written before copying, bundles files into password-protected encrypted archives, verifies byte-for-byte integrity using cryptographic checksums, and safely manages network bandwidth without operational oversight.
        </div>

        <h2>High-Level System Architecture</h2>
        <p>The application is divided into five robust layers designed for 24/7 unattended execution:</p>
        <ul>
            <li><b>1. Administrative Management Console:</b> Windows 11 Fluent desktop interface providing a multi-job overview (Main Dashboard), detailed file tracking (Job Workspace), system configuration (Settings), and live activity feeds.</li>
            <li><b>2. Central Orchestration Engine:</b> Manages multi-job scheduling, parallel folder scanning, sequential queue prioritization, and concurrent transfer pool limits.</li>
            <li><b>3. Real-Time Watchdog & Polling Services:</b> Continuously monitors source folders for new or modified files using native Windows filesystem event listeners paired with scheduled reconciliation sweeps.</li>
            <li><b>4. Background Helper Processes:</b> Heavy archive compression is offloaded to background helper processes. This guarantees that copying or compressing multi-gigabyte files will never freeze the user interface or slow down your workstation.</li>
            <li><b>5. Transactional History Database:</b> A local SQLite database configured with Write-Ahead Logging (WAL) that permanently logs every file transfer, timestamp, byte size, and verification checksum for compliance and auditing.</li>
        </ul>

        <h2>Application Directories & File Layout</h2>
        <table>
            <tr><th>Path</th><th>Description</th></tr>
            <tr><td><code>config/config.json</code></td><td>Application settings file (retry counts, transfer threads, archive passwords, cleanup policies).</td></tr>
            <tr><td><code>database/transfer_history.db</code></td><td>Embedded SQLite database storing job configurations and complete file transfer logs.</td></tr>
            <tr><td><code>logs/app.log</code></td><td>Automatic rolling log file recording system activities, network events, and error traces.</td></tr>
            <tr><td><code>FileTransferAutomationSystem.exe</code></td><td>Standalone compiled executable requiring no external Python installation.</td></tr>
        </table>
        """

    def _doc_user_guide(self) -> str:
        return """
        <h1>2. Admin User Guide (Step-by-Step Operations)</h1>
        <p>This section provides step-by-step instructions for IT administrators on how to set up, operate, and maintain file transfer jobs in daily operations.</p>

        <h2>Step 1: Creating a New Transfer Job</h2>
        <ol>
            <li>In the left sidebar, click <b>Add Job</b> (or click the <b>+ Add Job</b> button on the Main Dashboard).</li>
            <li><b>Job Name:</b> Enter a recognizable, unique name (e.g., <code>Branch 001 - Daily Invoices</code> or <code>CAD Drawings Backup</code>).</li>
            <li><b>Source Folder:</b> Select or type the folder path to be monitored. This can be a local path (<code>D:\\Exports</code>) or a Windows network share (<code>\\\\192.168.80.70\\Shared\\Data</code>).</li>
            <li><b>Destination Folder:</b> Select or type the target folder where transferred archives or files will be saved.</li>
            <li><b>Schedule Mode:</b>
                <ul>
                    <li><b>Continuous Mode:</b> Recommended for immediate processing. Files are transferred automatically as soon as they finish being written and pass lock checks.</li>
                    <li><b>Transfer Window Mode:</b> Recommended for scheduled batch backups (e.g., overnight). Files accumulate safely throughout the day, and at the configured <b>Window End</b> time (e.g., <code>18:00</code>), the system automatically bundles all accumulated files into an encrypted archive and transfers it in one batch.</li>
                </ul>
            </li>
            <li>Click <b>Save Job</b>. The new job card will immediately appear on the Main Dashboard.</li>
        </ol>

        <h2>Step 2: Starting, Pausing, and Monitoring Jobs</h2>
        <ul>
            <li><b>Start / Stop All:</b> Use the <b>Start All</b> and <b>Stop All</b> buttons at the top of the Main Dashboard to control all configured jobs with one click.</li>
            <li><b>Individual Job Control:</b> Each job card on the Main Dashboard has a dedicated <b>Start Monitoring / Stop Monitoring</b> button.</li>
            <li><b>Live Status:</b> The status badge on each card displays the current operational state (e.g., <code>MONITORING</code>, <code>TRANSFERRING</code>, <code>WAITING (OUTSIDE WINDOW)</code>).</li>
        </ul>

        <h2>Step 3: Manually Triggering Transfers ("Sync Now" & "Window Override")</h2>
        <p>If you need to transfer files immediately without waiting for the scheduled window time:</p>
        <ul>
            <li><b>Main Dashboard — Sync Now:</b> Click the <b>Sync Now</b> button on any job card. This immediately gathers all detected files and starts compression/transfer right away.</li>
            <li><b>Job Workspace — Window Override:</b> Navigate to the <b>Job Workspace</b> tab, select the job from the dropdown, select one or more files in the table that are in <code>WAITING_FOR_WINDOW</code> status, and click <b>Window Override</b>. The selected files will be transferred immediately.</li>
        </ul>

        <h2>Step 4: Viewing Transfer History & Audit Logs</h2>
        <ul>
            <li><b>Main Dashboard Live Feed:</b> The bottom panel displays a real-time event feed with timestamped notices of files detected, batch completions, and errors.</li>
            <li><b>Transfer History Dialog:</b> Click <b>Transfer History</b> in the sidebar to search, filter by date, and inspect past file transfers across all jobs.</li>
            <li><b>System Log Viewer:</b> Click <b>View Logs</b> in the bottom sidebar to inspect technical logs and diagnostic traces without having to open log files manually.</li>
        </ul>

        <h2>Step 5: Modifying Global Settings</h2>
        <p>Click <b>Settings</b> in the bottom-left sidebar to configure system-wide behavior:</p>
        <ul>
            <li><b>Zip Archive Password:</b> Change the encryption password for all future batch archives.</li>
            <li><b>Max Concurrent Transfers:</b> Set how many jobs are permitted to transfer simultaneously (recommended: <code>2</code> to <code>4</code>).</li>
            <li><b>Transfer Threads:</b> Set file-copy worker threads (default: <code>8</code>, recommended: <code>4</code> to <code>8</code> for network shares).</li>
            <li><b>Network Drive Mode:</b> Check this option when transferring across Windows network shares (UNC paths).</li>
            <li><b>Cleanup Retention (Days):</b> Configure how many days transferred files remain on the source machine before automated dual-verified cleanup (default: <code>7</code> days).</li>
        </ul>

        <h2>Step 6: Generating & Managing Corporate Daily Backup Checklists</h2>
        <p>To inspect and export the official corporate backup checklist for internal audit sign-off:</p>
        <ol>
            <li>Click <b>Daily Report</b> in the sidebar navigation.</li>
            <li><b>Calendar Picker:</b> Select the batch date you wish to inspect (defaults to today). The preview table and statistics cards update automatically.</li>
            <li><b>Checklist Configurator:</b> Click <b>Configure Checklist</b> to map test jobs (e.g. mapping test job <code>003</code> to official corporate row <code>TFA</code>), add extra systems, adjust file patterns, or change the default supervisor sign-off name (<b>Philip M. Bayudan</b>).</li>
            <li><b>Live Table Preview:</b> Review total transferred sizes, latest completion times, verification statuses, and automated SHA-256 cryptographic check results.</li>
            <li><b>Generate Excel Report:</b> Click <b>Generate Report (.xlsx)</b>. The system compiles the official checklist and saves it to <code>reports/TFSPH_Daily_Backup_Checklist_YYYY-MM-DD.xlsx</code>.</li>
            <li><b>Excel File Locking Note:</b> Because Microsoft Excel locks files on Windows when open, close Excel after viewing so automated background transfers can directly overwrite the primary checklist. If Excel remains open, the system automatically saves to <code>..._latest.xlsx</code> so updates are never lost.</li>
        </ol>
        """

    def _doc_statuses(self) -> str:
        return """
        <h1>3. Complete Status & Lifecycle Reference Guide</h1>
        <p>To avoid any confusion during administration, the system tracks status at <b>two distinct levels</b>:</p>
        <ol>
            <li><b>Job-Level Execution State</b> — Displayed as colored badges on the <b>Main Dashboard job cards</b>. Indicates what the overall job pipeline is currently doing.</li>
            <li><b>File-Level Lifecycle Status</b> — Displayed in the <b>Job Workspace table</b>, <b>Transfer History</b>, and the database. Tracks the exact stage of every individual file.</li>
        </ol>

        <h2>1. Job-Level Execution States (Main Dashboard Badges)</h2>
        <table>
            <tr><th>Badge</th><th>State</th><th>Operational Meaning</th></tr>
            <tr>
                <td><span class="badge" style="background-color: #EFF6FF; color: #1D4ED8;">TRANSFERRING</span></td>
                <td><b>Transferring</b></td>
                <td>The job is actively compressing files, copying bytes across the network, or calculating SHA-256 integrity checksums.</td>
            </tr>
            <tr>
                <td><span class="badge" style="background-color: #FFFBEB; color: #B45309;">QUEUED (IN LINE)</span></td>
                <td><b>Queued (In Line)</b></td>
                <td>Files are ready and waiting in line for another active transfer job to finish before this job begins.</td>
            </tr>
            <tr>
                <td><span class="badge" style="background-color: #F0FDF4; color: #15803D;">MONITORING</span></td>
                <td><b>Monitoring</b></td>
                <td>The background watcher is active and listening for new files created or copied into the source folder.</td>
            </tr>
            <tr>
                <td><span class="badge" style="background-color: #FFFBEB; color: #92400E;">WAITING (OUTSIDE WINDOW)</span></td>
                <td><b>Waiting for Window</b></td>
                <td>Files have been detected and verified stable, but the job is configured with a Transfer Window. Files are holding safely until the scheduled Window End time.</td>
            </tr>
            <tr>
                <td><span class="badge" style="background-color: #F3F4F6; color: #4B5563;">IDLE / STOPPED</span></td>
                <td><b>Idle / Paused</b></td>
                <td>Monitoring is inactive or paused by the administrator. No automatic file detection will occur.</td>
            </tr>
        </table>

        <h2>2. File-Level Lifecycle Statuses (Job Workspace & History)</h2>
        <table>
            <tr><th>Status Code</th><th>Status Name</th><th>Detailed Lifecycle Explanation</th></tr>
            <tr>
                <td><code>DETECTED</code></td>
                <td><b>Detected</b></td>
                <td>A new file was discovered in the source folder. The system is performing initial checks to see if the file is still being copied or written by another application.</td>
            </tr>
            <tr>
                <td><code>PROCESSING</code></td>
                <td><b>Stabilizing / In-Progress</b></td>
                <td>The system is actively checking file size over consecutive intervals to confirm the file has finished downloading or writing. Also used while a file is actively being packaged into an archive.</td>
            </tr>
            <tr>
                <td><code>WAITING_FOR_WINDOW</code></td>
                <td><b>Waiting for Window</b></td>
                <td>The file is completely finished, stable, and unlocked, but is waiting for the scheduled backup window (e.g., <code>18:00</code>) to transfer.</td>
            </tr>
            <tr>
                <td><code>READY</code></td>
                <td><b>Ready to Transfer</b></td>
                <td>The file has passed all stability and Windows lock checks. It is staged and ready to be dispatched for transfer.</td>
            </tr>
            <tr>
                <td><code>QUEUED</code></td>
                <td><b>Queued in Batch</b></td>
                <td>The file has been assigned to an outgoing batch request and is queued in memory waiting for worker execution.</td>
            </tr>
            <tr>
                <td><code>TRANSFERRING</code></td>
                <td><b>Transferring Bytes</b></td>
                <td>The file's bytes are actively streaming across the network or being compressed into the destination archive.</td>
            </tr>
            <tr>
                <td><code>VERIFYING</code></td>
                <td><b>Verifying Checksum</b></td>
                <td>The transfer is physically complete; the system is reading both copies to compute and compare SHA-256 cryptographic hashes.</td>
            </tr>
            <tr>
                <td><code>COMPLETED</code></td>
                <td><b>Completed & Verified</b></td>
                <td>The file transfer succeeded 100%. The destination file exists and its SHA-256 hash perfectly matches the source file.</td>
            </tr>
            <tr>
                <td><code>FAILED</code></td>
                <td><b>Transfer Failed</b></td>
                <td>An error occurred during transfer (e.g., network disconnected, destination disk full, or file access denied). The system logs the specific error message and will retry based on your retry configuration.</td>
            </tr>
            <tr>
                <td><code>SKIPPED</code></td>
                <td><b>Skipped</b></td>
                <td>The file was intentionally omitted. Common reasons: the identical file was already transferred previously (duplicate detection), or the file was deleted by an operator before the transfer began.</td>
            </tr>
            <tr>
                <td><code>CONFLICT</code></td>
                <td><b>File Conflict</b></td>
                <td>A file with the same name exists at the destination but has a different size or timestamp. Handled according to your Overwrite Policy in Settings.</td>
            </tr>
        </table>
        """

    def _doc_transfer_engine(self) -> str:
        return """
        <h1>4. File Transfer Engine & Safe Copy Protocol</h1>
        <p>Enterprise data transfers must be resilient against power cuts, network hiccups, and corrupted bytes. Here is how the system guarantees data safety:</p>

        <h2>Transfer Modes: Batch Archive vs. Direct Copy</h2>
        <ul>
            <li><b>Batch Archive Mode (Default & Recommended):</b> Consolidates all queued files into a single password-protected, encrypted ZIP archive directly on the destination server. Perfect for backing up hundreds of files with minimum network overhead.</li>
            <li><b>Direct Copy Mode:</b> When batch compression is turned off in Settings, files are copied individually as standard files using streaming multi-threaded buffers.</li>
        </ul>

        <h2>The Atomic "Safe Copy" Strategy</h2>
        <div class="callout-info">
            <b>Problem it Solves:</b> In standard Windows file copying, if a network disconnect occurs midway, you are left with a broken, half-copied file that looks complete but cannot be opened.
        </div>
        <p>To prevent this, the system follows a 4-step atomic staging protocol:</p>
        <ol>
            <li><b>Hidden Temporary Staging:</b> Files are never written directly to their final filename. They are written to a hidden temporary file at the destination:
                <br><code>{destination}/.{filename}.transfer_tmp</code>
            </li>
            <li><b>Chunked Streaming:</b> Files are read and written in efficient 64 KB binary chunks. This allows transferring 50 GB+ files without exhausting computer RAM.</li>
            <li><b>End-to-End SHA-256 Verification:</b> Once the file is written, both source and destination copies are cryptographically hashed. If even 1 byte differs, the temporary file is deleted immediately.</li>
            <li><b>Atomic Commit:</b> Once hashes match 100%, Windows instantly renames the temporary file to its final destination name. Only complete, verified files ever become visible.</li>
        </ol>

        <h2>Network Bandwidth & Multi-Job Concurrency</h2>
        <p>In <b>Settings</b>, you can configure:</p>
        <ul>
            <li><b>Max Concurrent Transfers (default: <code>3</code>):</b> Allows up to 3 jobs to transfer at once. Additional jobs wait in an orderly FIFO queue. As soon as one job finishes, the next queued job begins immediately.</li>
            <li><b>Transfer Threads (default: <code>4</code>):</b> Controls parallel copy streams per job. Configured specifically to maximize speed without saturating your office network.</li>
        </ul>
        """

    def _doc_compression(self) -> str:
        return """
        <h1>5. Archiving, Encryption & Passwords</h1>
        <p>When batch compression is enabled, accumulated files are packaged into secure, password-protected ZIP archives.</p>

        <h2>Why We Archive Files</h2>
        <ul>
            <li><b>Consolidation:</b> Bundles hundreds of separate files into one clean, timestamped archive (e.g., <code>2026-09-04_180000.zip</code>).</li>
            <li><b>Network Efficiency:</b> Copying one consolidated 1 GB file across a network is up to <b>10 times faster</b> than copying 10,000 tiny 100 KB files due to network protocol overhead.</li>
            <li><b>Security:</b> Protects sensitive corporate data in transit and at rest with strong encryption.</li>
        </ul>

        <h2>Military-Grade AES-256 Encryption & Zip64</h2>
        <ul>
            <li><b>WinZip AES-256 Standard:</b> The application encrypts archives using standard WinZip AES-256 / AES-128 encryption powered by <code>pyzipper</code>. This provides robust protection against unauthorized access.</li>
            <li><b>Zip64 Support (No 4 GB Limit):</b> Standard legacy zip files cannot exceed 4 GB. This system includes native <b>Zip64</b> support, allowing you to generate massive archives exceeding 50 GB to 500 GB+ without failure.</li>
            <li><b>Fallback Compatibility:</b> If needed, the system automatically falls back to standard <code>pyminizip</code> / standard <code>zipfile</code> to ensure an archive is always generated.</li>
        </ul>

        <h2>How to Open & Extract Archives</h2>
        <p>Transferred archives can be opened on any PC using standard file archivers:</p>
        <ul>
            <li><b>7-Zip (Recommended):</b> Right-click the <code>.zip</code> file &rarr; <b>7-Zip</b> &rarr; <b>Extract to...</b> &rarr; Enter your configured password.</li>
            <li><b>WinRAR:</b> Double-click the archive &rarr; Enter password when prompted.</li>
            <li><b>Windows Explorer:</b> Native Windows Explorer supports extraction directly if standard encryption is used.</li>
        </ul>

        <h2>Managing the Archive Password</h2>
        <p>To view or change the archive password:</p>
        <ol>
            <li>Open the application and click <b>Settings</b> in the bottom-left sidebar.</li>
            <li>Locate the <b>Zip Archive Password</b> field.</li>
            <li>Type your new corporate password (up to 128 characters) and click <b>Save Settings</b>.</li>
            <li>All future batch archives will immediately use the updated password.</li>
        </ol>
        """

    def _doc_safety_locks(self) -> str:
        return """
        <h1>6. File Safety & In-Use File Protection</h1>
        <p>A frequent problem in automated file transfer systems is attempting to copy files that are still being saved, rendered, or exported by another program (such as accounting software, CAD tools, or video recorders).</p>

        <h2>1. Windows File Lock Detection</h2>
        <p>Before touching any file, the system requests an exclusive low-level Windows file handle. If another program is still writing to or has the file open:</p>
        <ul>
            <li>Windows flags the file as locked.</li>
            <li>The system leaves the file untouched and skips copying it.</li>
            <li>The file remains in <code>DETECTED</code> status until the other software finishes and closes the file handle.</li>
        </ul>

        <h2>2. Consecutive Stability Check Cycles</h2>
        <p>Even if a file is unlocked, it might be downloading slowly or growing in size:</p>
        <ul>
            <li>The system records the file's exact byte count.</li>
            <li>It waits for the <b>Stability Check Interval</b> (default: <code>5</code> seconds).</li>
            <li>It checks the byte count again.</li>
            <li>The file must maintain the <b>exact same size</b> across <code>2</code> consecutive checks before it is declared stable and ready to transfer.</li>
        </ul>

        <h2>3. Mid-Transfer Deletion Safeguard & Automated Clean Restart</h2>
        <div class="callout-warning">
            <b>Scenario:</b> What happens if an employee deletes a file from the source folder while the system is in the middle of compressing a 2 GB archive?
        </div>
        <p>In older systems, this would cause a crash or result in a corrupted archive. In this application:</p>
        <ul>
            <li>A background safety monitor checks file existence every 500ms during compression.</li>
            <li>If an active file is deleted mid-transfer, the system immediately terminates the compression helper process.</li>
            <li>The partial, invalid <code>.zip</code> file is destroyed immediately so no corrupted file remains.</li>
            <li>The deleted file is marked as <code>SKIPPED</code> in the database.</li>
            <li>The system posts a notice in the live activity feed: <i>"File was deleted mid-compression. Discarded partial archive; automatically restarting..."</i></li>
            <li>The system automatically restarts cleanly with the remaining valid files without any administrator intervention needed!</li>
        </ul>
        """

    def _doc_network_shares(self) -> str:
        return """
        <h1>7. Network Shares (SMB / UNC) Configuration & Thread Tuning</h1>
        <p>The system is specifically optimized for Windows Network Shares (SMB) and Uniform Naming Convention (UNC) paths (e.g., <code>\\\\Server01\\SharedFolder\\Backups</code>).</p>

        <h2>Best Practices for Network Paths</h2>
        <ul>
            <li><b>Always Use UNC Paths Instead of Mapped Drive Letters:</b>
                <br>Use <code>\\\\192.168.80.70\\Backups</code> instead of <code>Z:\\Backups</code>. Windows mapped drive letters are tied to individual user login sessions and can disconnect when running unattended. UNC paths remain reliable 24/7.
            </li>
            <li><b>Ensure Network Share & NTFS Permissions:</b>
                <br>The Windows user account running the application must have <b>Read</b> permissions on the Source folder and <b>Write/Modify</b> permissions on the Destination folder.
            </li>
            <li><b>Enable Network Drive Mode in Settings:</b>
                <br>In <b>Settings</b>, make sure <b>Network Drive Mode</b> is checked (<code>true</code>). This optimizes polling intervals and directory scanning routines specifically for network latency.
            </li>
        </ul>

        <h2>Understanding Transfer Threads: Detailed Technical Breakdown</h2>
        <p>In <b>Settings</b>, the <b>Transfer Threads</b> option controls how many individual files can be copied simultaneously side-by-side during direct file transfers.</p>
        <p>Here is an in-depth breakdown of what each thread level means for your network infrastructure:</p>

        <table>
            <tr><th>Thread Setting</th><th>Operating Characteristics</th><th>Recommended Environments</th><th>Pros & Cons</th></tr>
            <tr>
                <td><b>1 Thread</b><br>(Sequential)</td>
                <td>Copies files strictly one-by-one in sequential order. No parallel streaming.</td>
                <td>Weak Wi-Fi connections, remote VPN links, or older spinning mechanical hard drives (HDDs).</td>
                <td><b>Pros:</b> Zero network or disk contention.<br><b>Cons:</b> Leaves modern gigabit bandwidth under-utilized when transferring many files.</td>
            </tr>
            <tr>
                <td><b>2 Threads</b><br>(Light Parallelism)</td>
                <td>Copies 2 files simultaneously side-by-side.</td>
                <td>Modest branch office networks, entry-level dual-core servers, or low-bandwidth connections.</td>
                <td><b>Pros:</b> Very gentle on network routers and server CPU.<br><b>Cons:</b> Slower than 4 threads on gigabit local networks.</td>
            </tr>
            <tr>
                <td><b>4 Threads</b><br><b>(Enterprise Sweet Spot)</b></td>
                <td>Copies 4 files simultaneously. Achieves optimal network throughput while staying safely within Windows SMB socket credit limits.</td>
                <td>Standard corporate 1 Gbps LAN networks, Windows File Servers, Synology/QNAP NAS devices, and modern quad-core/octa-core PCs.</td>
                <td><b>Pros:</b> Maximizes gigabit line speed without exhausting SMB connection credits or overloading the server's disk queue. Rock-solid stability.<br><b>Cons:</b> None on standard enterprise LANs.</td>
            </tr>
            <tr>
                <td><b>8 Threads</b><br><b>(Configured Default)</b></td>
                <td>Copies 8 files simultaneously per job across the thread pool.</td>
                <td>Modern multi-core enterprise workstations, NVMe SSDs, high-throughput network backbones, and server storage.</td>
                <td><b>Pros:</b> Achieves maximum saturation of gigabit and multi-gigabit connections.<br><b>Note:</b> Coupled with the system's 600ms event debouncer and SQLite WAL mode, 8 concurrent threads run smoothly without GUI locking.</td>
            </tr>
            <tr>
                <td><b>16+ Threads</b><br>(Enterprise SAN Only)</td>
                <td>Massive parallel streaming.</td>
                <td>Enterprise Storage Area Networks (SAN) with 10 GbE / 40 GbE fiber and SMB Multichannel configured.</td>
                <td><b>Warning:</b> On normal office networks, setting 16+ threads actually degrades speed due to packet collisions and thread queue overhead.</td>
            </tr>
        </table>

        <h2>Transfer Threads vs. Max Concurrent Transfers</h2>
        <div class="callout-info">
            <b>Key Distinction:</b>
            <br>&bull; <b>Max Concurrent Transfers:</b> Controls how many <b>different Jobs</b> (e.g. Job 1, Job 2, Job 3) can run at the same time (default: <code>3</code>).
            <br>&bull; <b>Transfer Threads:</b> Controls how many <b>individual files</b> inside a direct-transfer job are copied at once (default: <code>8</code>).
        </div>

        <h2>Network Disconnect Resilience</h2>
        <p>If a network cable is unplugged or a Wi-Fi/VPN connection briefly drops:</p>
        <ul>
            <li>The system checks if the root server share is reachable before testing file existence.</li>
            <li>If the server is temporarily unreachable, the system safely pauses checks instead of falsely assuming files were deleted.</li>
            <li>Individual file checks include a 50ms confirmation buffer to ignore momentary network blips.</li>
        </ul>
        """

    def _doc_cleanup(self) -> str:
        return """
        <h1>8. Source File Cleanup & Retention Policy</h1>
        <p>To prevent source drives (especially on high-volume production machines) from running out of disk space, the system includes an automated, safe cleanup mechanism.</p>

        <h2>The Dual-Verification Rule</h2>
        <div class="callout-danger">
            <b>Zero Accidental Data Loss Guarantee:</b> Source files are NEVER deleted unless all three of the following conditions are strictly verified:
        </div>
        <ol>
            <li><b>Age Requirement:</b> The file was successfully transferred at least <i>N</i> days ago (configured via <b>Cleanup Retention Days</b>, default: <code>7</code> days).</li>
            <li><b>Verified Destination Existence:</b> The system verifies in the SQLite database that the transfer is marked <code>COMPLETED</code> and checks that the file or archive physically exists at the destination path.</li>
            <li><b>Source Existence:</b> The original file is still present at the source.</li>
        </ol>

        <h2>How to Configure or Disable Cleanup</h2>
        <ol>
            <li>Open the application and click <b>Settings</b> in the bottom-left sidebar.</li>
            <li><b>To Enable/Disable:</b> Check or uncheck <b>Enable Automatic Source Cleanup</b>. (If unchecked, source files are never deleted).</li>
            <li><b>Retention Period:</b> In the <b>Cleanup Retention (Days)</b> box, enter the number of days to keep files (e.g., <code>7</code>, <code>14</code>, <code>30</code>, or <code>90</code> days).</li>
            <li>Click <b>Save Settings</b>.</li>
        </ol>
        """

    def _doc_troubleshooting(self) -> str:
        return """
        <h1>9. IT Troubleshooting & Practical FAQ</h1>
        <p>This handbook provides actionable, step-by-step troubleshooting procedures for IT administrators handling real-world scenarios.</p>

        <h2>Troubleshooting Scenarios</h2>

        <h3>Scenario 1: A file shows "FAILED" status in the Job Workspace</h3>
        <p><b>Cause:</b> Network dropped during transfer, destination disk ran out of space, or a file permission error occurred.</p>
        <p><b>How to Troubleshoot & Fix:</b></p>
        <ol>
            <li>Navigate to the <b>Job Workspace</b> tab.</li>
            <li>Select the affected job from the dropdown.</li>
            <li>In the table, look at the <b>Status</b> column (it will show <code>FAILED</code>) and read the <b>Error Message</b> column to see the exact error.</li>
            <li>Click <b>View Logs</b> in the bottom sidebar to inspect detailed error logs.</li>
            <li>Once the underlying cause is resolved (e.g. disk space cleared or network restored), select the failed file and click <b>Retry Failed</b>. The system will immediately re-queue the file for transfer.</li>
        </ol>

        <h3>Scenario 2: Files in the source folder are not being detected</h3>
        <p><b>How to Troubleshoot:</b></p>
        <ol>
            <li><b>Check Job Status:</b> On the Main Dashboard, verify that the job badge displays <code>MONITORING</code>. If it says <code>IDLE / STOPPED</code>, click <b>Start Monitoring</b>.</li>
            <li><b>Check if File is Still Open / In Use:</b> If another program is actively writing to the file, the system deliberately waits for it to finish. Close the file in the other application.</li>
            <li><b>Check Transfer History (Duplicate Prevention):</b> If the exact same file (matching filename, size, and modified date) was already transferred previously, the system intentionally skips it. Check the <b>Transfer History</b> dialog.</li>
            <li><b>Verify Folder Path:</b> Click <b>Edit Job</b> and make sure the source folder path is correct and accessible.</li>
        </ol>

        <h3>Scenario 3: "Access Denied" or Permission Errors on Network Shares</h3>
        <p><b>Cause:</b> The Windows user account running the application lacks read or write rights on the shared folder.</p>
        <p><b>How to Troubleshoot & Fix:</b></p>
        <ol>
            <li>Open Windows File Explorer and try to manually browse to both the source (<code>\\\\Server\\Source</code>) and destination (<code>\\\\Server\\Destination</code>) paths.</li>
            <li>Try to manually create a new text file in the destination folder to confirm write permissions.</li>
            <li>If Windows prompts for credentials, check <i>"Remember my credentials"</i> in Windows Credential Manager.</li>
            <li>Ask your network administrator to grant <b>Modify / Write</b> permissions on the destination network share.</li>
        </ol>

        <h3>Scenario 4: Need to Re-Transfer a File that was Accidentally Deleted at Destination</h3>
        <p><b>How to Troubleshoot & Fix:</b></p>
        <ol>
            <li>Go to the <b>Job Workspace</b> tab.</li>
            <li>Find the file in the table. Even if it shows <code>COMPLETED</code>, you can select the file and click <b>Window Override</b> or click <b>Sync Now</b> on the Main Dashboard to force an immediate re-transfer.</li>
            <li>If the file was already cleaned up from source according to retention policy, you can restore it from your regular destination backup archive.</li>
        </ol>

        <h3>Scenario 5: Computer or Server Restarted Unexpectedly During Transfer</h3>
        <p><b>What Happens & How to Recover:</b></p>
        <ul>
            <li><b>Automatic Crash Recovery:</b> The application was designed with automatic crash recovery. When the application starts up again, it scans SQLite for any transfers that were interrupted mid-flight.</li>
            <li><b>Zero Partial Files:</b> Because of atomic staging, any unfinished temporary files (<code>.tmp</code> or partial <code>.zip</code>) are automatically cleaned up. Destination files are never corrupted.</li>
            <li><b>Resumption:</b> Unfinished files automatically reset to <code>READY</code> status and will transfer on the next cycle or when you click <b>Sync Now</b>.</li>
        </ul>

        <h3>Scenario 6: Destination Drive Running Low on Space</h3>
        <p><b>How to Troubleshoot & Fix:</b></p>
        <ol>
            <li>Check the available free disk space on the destination drive.</li>
            <li>If space is low, archive older completed backup <code>.zip</code> files to external cold storage or tapes.</li>
            <li>In <b>Settings</b>, review your <b>Cleanup Retention (Days)</b> to ensure old source files are being pruned properly.</li>
        </ol>

        <h3>Scenario 7: How to Run Automatically on Windows Startup</h3>
        <p>To ensure the application runs continuously without requiring someone to log in and open it manually:</p>
        <ol>
            <li>Press <code>Win + R</code>, type <code>shell:startup</code>, and press Enter.</li>
            <li>Paste a shortcut to <code>FileTransferAutomationSystem.exe</code> in this folder.</li>
            <li>Open the application, click <b>Settings</b>, and ensure <b>Start Monitoring on Launch</b> is checked (<code>true</code>).</li>
            <li>Now, whenever Windows boots and logs in, the application starts and begins monitoring all enabled jobs automatically.</li>
        </ol>

        <h3>Scenario 8: Microsoft Excel File Lock ([Errno 13] Permission denied) & Fallback Saving</h3>
        <p><b>Cause:</b> An operator or supervisor currently has the generated daily report open in Microsoft Excel on Windows.</p>
        <p><b>Technical Details & Resolution:</b></p>
        <ul>
            <li><b>Windows Exclusive File Locking:</b> When Microsoft Excel opens any <code>.xlsx</code> workbook on Windows, it obtains an exclusive operating system write lock. Any external software (like Python or openpyxl) attempting to modify or overwrite that file is blocked with <code>[Errno 13] Permission denied</code>.</li>
            <li><b>Excel In-Memory Buffering:</b> Furthermore, Microsoft Excel does not poll the file system or reload modified files while open. Even if an external program wrote to the disk, Excel would discard those changes upon closing or saving.</li>
            <li><b>Automated Fallback to <code>..._latest.xlsx</code>:</b> Instead of crashing or throwing an unhandled exception, the system catches the Windows lock error, writes the fresh report to a designated fallback file:
                <br><code>reports/TFSPH_Daily_Backup_Checklist_&lt;YYYY-MM-DD&gt;_latest.xlsx</code>
            </li>
            <li><b>Operator Notification:</b> A yellow Warning InfoBar pops up in the UI: <i>"Original report file is currently open in Microsoft Excel. Saved latest copy to ..._latest.xlsx. Close Excel to overwrite primary report."</i></li>
            <li><b>How to Update Primary Report:</b> Simply close Microsoft Excel and click <b>Generate Report (.xlsx)</b> again or wait for the next automated window completion.</li>
        </ul>

        <h3>Scenario 9: Multi-File Batch Jobs Total Size Calculation & Timestamp Accuracy</h3>
        <p><b>Question:</b> Why does a job containing multiple files display only a few bytes, or how does the checklist calculate the total size?</p>
        <p><b>How It Works:</b></p>
        <ul>
            <li>In real-world production or test environments, a job may transfer multiple files (e.g., <code>003_part1.dat</code>, <code>003_part2.dat</code>, etc.).</li>
            <li>The Daily Report service computes the true aggregated byte sum across all successful transfer records for that job (<code>sum(r.file_size)</code>). If a job transferred three 100 MB files, the checklist accurately reports <code>300.0 MB</code>.</li>
            <li>The completion timestamp in Column G (<b>Time of Completion</b>) reflects the <b>latest completion timestamp</b> among all files in the batch, guaranteeing audit integrity.</li>
            <li>If a job was paused and restarted, or files were deleted, only valid, completed transfers for that batch date are summed.</li>
        </ul>

        <h3>Scenario 10: Operator Workflow — Pause &rarr; Delete &rarr; Start &rarr; Sync Now</h3>
        <p><b>Question:</b> What happens to the daily report if an operator pauses a job, deletes files from the source folder, starts the job, and triggers Sync Now?</p>
        <p><b>Lifecycle Behavior:</b></p>
        <ol>
            <li><b>Pause:</b> Halts the active filesystem watcher. Staged files hold in place.</li>
            <li><b>Delete from Source:</b> When files are removed from the source folder while paused, the physical files no longer exist on disk.</li>
            <li><b>Start Monitoring & Sync Now:</b> The transfer engine executes a pre-flight existence sweep. It immediately detects that the deleted files are absent, logs them as <code>SKIPPED</code>, and removes them from active staging.</li>
            <li><b>Transfer Execution:</b> Any remaining valid files in the source folder transfer cleanly and complete with SHA-256 integrity verification.</li>
            <li><b>Real-Time Report Sync:</b> The application's 600ms debouncer triggers upon transfer completion, instantly updating the Daily Report live preview table and generating a fresh Excel checklist without requiring an application restart.</li>
        </ol>

        <h3>Scenario 11: Multi-Job Concurrency, Thread Pool (8 Threads), and GUI Responsiveness</h3>
        <p><b>Question:</b> Can running 3 jobs simultaneously with 8 worker threads freeze or lag the user interface?</p>
        <p><b>Engineering Safeguards:</b></p>
        <ul>
            <li><b>600ms Debounced Event Timer:</b> During fast multi-job transfers, dozens of transfer completion signals arrive in rapid succession. Instead of rebuilding UI tables on every single file (which can freeze Qt), the system buffers events with a 600ms timer (<code>_report_refresh_timer</code>), consolidating multiple updates into a single fluid UI repaint.</li>
            <li><b>Background Report Generation:</b> Report compiling and Excel rendering run asynchronously in a daemon background thread (<code>threading.Thread</code>), keeping the main GUI thread completely unblocked.</li>
            <li><b>SQLite Write-Ahead Logging (WAL):</b> Multi-threaded database operations execute with thread-safe write locks and WAL journal mode, preventing database lock errors (<code>sqlite3.OperationalError: database is locked</code>).</li>
            <li><b>Cached Network Checks:</b> SMB/UNC directory capacity queries are cached for 60 seconds to avoid blocking when inspecting remote file servers.</li>
        </ul>

        <h2>Frequently Asked Questions (FAQ)</h2>

        <h3>Q: Why is there a slight initial delay when transferring large files (e.g. 1.9 GB) compared to 50 MB files?</h3>
        <p><b>A:</b> This is completely normal and expected behavior in file systems. Compressing and transferring a 1.9 GB file requires reading and digesting 1,900,000,000 bytes across network sockets into CPU compression buffers. While a 50 MB batch finishes in 1–2 seconds, a 1.9 GB batch takes 20–30 seconds. The system immediately displays <code>Compressing Archive (0% · 0.0 MB / 1900.0 MB)</code> on millisecond 0 to confirm active processing.</p>

        <h3>Q: Can multiple jobs transfer at the same time?</h3>
        <p><b>A:</b> Yes. In <b>Settings</b>, the <b>Max Concurrent Transfers</b> setting (default: <code>3</code>) allows multiple jobs to run in parallel. If more jobs trigger than the limit, extra jobs wait in an orderly queue and start automatically as soon as an active job finishes.</p>

        <h3>Q: Will this slow down my network or freeze my computer?</h3>
        <p><b>A:</b> No. Heavy compression is offloaded to a background helper process so your desktop interface remains at a smooth 40–60 FPS. Direct transfers default to 8 worker threads with throttled GUI signal dispatchers (capped at 100ms) and a 600ms report refresh debouncer, ensuring peak throughput without UI freezes.</p>

        <h3>Q: What should I do if the Daily Report says "Saved latest copy to ..._latest.xlsx"?</h3>
        <p><b>A:</b> This means you or someone else has the primary report workbook (<code>TFSPH_Daily_Backup_Checklist_YYYY-MM-DD.xlsx</code>) open in Microsoft Excel. Close Excel so Windows releases the file lock, then click <b>Generate Report (.xlsx)</b> in the Daily Report toolbar to overwrite the primary report with the latest figures.</p>
        """

    def _doc_testing_guide(self) -> str:
        return """
        <h1>10. Admin Verification & Testing Guide</h1>
        <p>As an IT administrator, you should never have to take safety claims on faith. Here are <b>easy, practical tests</b> you can perform right on your workstation to observe all built-in safeguards in real time:</p>

        <h2>Test 1: Verifying the SKIPPED Status (Duplicate File Prevention)</h2>
        <p><b>Goal:</b> Prove that the system prevents redundant transfers and correctly marks duplicates as <code>SKIPPED</code>.</p>
        <ol>
            <li>Create a simple text file named <code>invoice_test.txt</code> in your job's Source folder.</li>
            <li>Click <b>Sync Now</b> on the Main Dashboard. The file transfers and is marked <code>COMPLETED</code>.</li>
            <li>Leave the file in the Source folder without changing it, and click <b>Sync Now</b> again.</li>
            <li><b>Observed Result:</b> Open the <b>Job Workspace</b> tab. You will see that the system recognized the identical file size and modified timestamp, refused to waste network bandwidth re-copying it, and logged its status as <code>SKIPPED</code>.</li>
        </ol>

        <h2>Test 2: Verifying the Mid-Transfer Deletion Safeguard & Auto-Restart</h2>
        <p><b>Goal:</b> Prove that deleting a file while compression is actively underway destroys the partial archive and automatically restarts without errors.</p>
        <ol>
            <li>Place two or three medium/large files (e.g. video files, large PDFs, or ISO files totaling 500 MB to 1 GB) plus one small file named <code>delete_me_now.txt</code> into your Source folder.</li>
            <li>Click <b>Sync Now</b> to start compression. The job card will display <code>TRANSFERRING</code> and the progress bar will begin moving (e.g., 10%... 20%).</li>
            <li>While the progress bar is actively moving, open Windows File Explorer and <b>delete <code>delete_me_now.txt</code></b> from the Source folder.</li>
            <li><b>Observed Result:</b>
                <ul>
                    <li>Within 500ms, the system detects that <code>delete_me_now.txt</code> was deleted.</li>
                    <li>The compression helper process is immediately killed and the partial temporary <code>.zip</code> file is destroyed.</li>
                    <li>The Live Activity Feed posts an immediate notice: <i>"File 'delete_me_now.txt' was deleted from folder... Discarded partial archive; automatically restarting..."</i></li>
                    <li>The worker cleanly restarts compression with only the remaining files, finishing 100% successfully with zero admin intervention!</li>
                </ul>
            </li>
        </ol>

        <h2>Test 3: Verifying Windows In-Use File Lock Detection</h2>
        <p><b>Goal:</b> Prove that the system will not transfer an incomplete file that is still open in another application.</p>
        <ol>
            <li>Open Microsoft Excel or Word (or a large CAD/video application).</li>
            <li>Save a new file directly into your Source folder, but <b>keep the program open</b> with the document actively loaded.</li>
            <li>Check the <b>Job Workspace</b> tab.</li>
            <li><b>Observed Result:</b> The file will be detected, but the system will recognize the open Windows lock handle and refuse to transfer it prematurely. The file will hold safely until you close the application, at which point it automatically stabilizes and transfers.</li>
        </ol>

        <h2>Test 4: Verifying Automated Source File Retention Cleanup</h2>
        <p><b>Goal:</b> Prove that the dual-verification rule safely deletes old source files only after confirming destination existence.</p>
        <ol>
            <li>Click <b>Settings</b> in the sidebar.</li>
            <li>Ensure <b>Enable Automatic Source Cleanup</b> is checked.</li>
            <li>Temporarily set <b>Cleanup Retention (Days)</b> to <code>0</code> (this makes files completed today immediately eligible for cleanup).</li>
            <li>Click <b>Save Settings</b>.</li>
            <li>Transfer a test file (e.g., <code>cleanup_test.txt</code>). Once it reaches <code>COMPLETED</code> and the destination archive exists:</li>
            <li><b>Observed Result:</b> The retention cleaner verifies that the destination archive exists and is valid, then cleans up <code>cleanup_test.txt</code> from the source folder, logging: <i>"Source file 'cleanup_test.txt' safely cleaned up per retention policy"</i>.</li>
            <li><b>Important:</b> After testing, return to Settings and set your retention back to your preferred policy (e.g. <code>7</code> days).</li>
        </ol>

        <h2>Test 5: Verifying Network Disconnect Resilience</h2>
        <p><b>Goal:</b> Prove that a brief network drop will not cause the system to falsely report files as deleted.</p>
        <ol>
            <li>Configure a job with a network UNC path (e.g., <code>\\\\192.168.80.70\\Share</code>).</li>
            <li>Briefly disconnect your network connection (unplug cable or toggle Wi-Fi for 3 seconds), then reconnect.</li>
            <li><b>Observed Result:</b> The system tests root share reachability. Because the server was temporarily unreachable, it skips the sweep instead of falsely reporting files as deleted. When the network reconnects, monitoring resumes seamlessly without false alarms.</li>
        </ol>

        <h2>Test 6: Verifying Daily Backup Checklist & Linked Job Mapping</h2>
        <p><b>Goal:</b> Prove that test jobs (e.g., <code>001</code> to <code>006</code>) automatically populate the official corporate checklist systems (<code>TFS42PROD</code>, <code>CSE</code>, <code>TFA</code>, etc.) with accurate aggregated sizes and cryptographic integrity status.</p>
        <ol>
            <li>Click <b>Daily Report</b> in the sidebar navigation, then click <b>Configure Checklist</b>.</li>
            <li>Verify the <b>Linked Job</b> mappings (e.g., <code>001</code> &rarr; <code>TFS42PROD</code>, <code>002</code> &rarr; <code>CSE</code>, <code>003</code> &rarr; <code>TFA</code>, <code>004</code> &rarr; <code>COGNOS</code>, <code>005</code> &rarr; <code>SAP</code>, <code>006</code> &rarr; <code>GOCANVAS</code>). Click <b>Save</b>.</li>
            <li>Navigate to the Main Dashboard and trigger a transfer on job <code>001</code> (or click <b>Sync Now</b>).</li>
            <li>Once the transfer completes, switch back to the <b>Daily Report</b> tab.</li>
            <li><b>Observed Result:</b>
                <ul>
                    <li>The live preview table automatically refreshes (via the 600ms debouncer) without requiring an application restart.</li>
                    <li>Row 1 (<code>TFS42PROD</code>) now displays the formatted filename matching the corporate pattern (without <code>.zip</code>), the true aggregated byte size across all transferred files (e.g. <code>345.5 MB</code>), the latest completion timestamp, status <code>COMPLETED</code>, and SHA-256 integrity check <code>Passed</code>!</li>
                </ul>
            </li>
        </ol>

        <h2>Test 7: Verifying Microsoft Excel File Lock Safeguard & Fallback Saving</h2>
        <p><b>Goal:</b> Prove that when the daily report workbook is held open in Microsoft Excel, background generation saves to <code>_latest.xlsx</code> without crashing or dropping data.</p>
        <ol>
            <li>In the <b>Daily Report</b> tab, click <b>Generate Report (.xlsx)</b>. The system opens the generated workbook in Microsoft Excel.</li>
            <li><b>Leave Microsoft Excel open</b> with the spreadsheet displayed on your screen.</li>
            <li>Switch back to the File Transfer Automation application and click <b>Generate Report (.xlsx)</b> again (or trigger a job transfer).</li>
            <li><b>Observed Result:</b>
                <ul>
                    <li>The system detects the exclusive Windows Excel file lock (<code>[Errno 13] Permission denied</code>).</li>
                    <li>Instead of crashing, the system gracefully writes the fresh workbook to <code>reports/TFSPH_Daily_Backup_Checklist_&lt;YYYY-MM-DD&gt;_latest.xlsx</code>.</li>
                    <li>A warning notification displays: <i>"Original report file is currently open in Microsoft Excel. Saved latest copy to ..._latest.xlsx. Close Excel to overwrite primary report."</i></li>
                    <li>Close Microsoft Excel and click <b>Generate Report (.xlsx)</b> again. The primary workbook is now cleanly overwritten with zero lock errors!</li>
                </ul>
            </li>
        </ol>
        """

    def _doc_daily_report(self) -> str:
        return """
        <h1>TFSPH Daily Backup Checklist & Executive Report Guide</h1>
        <p>This section provides comprehensive instructions for the <b>Daily Report</b> interface, automated checklist generation, and audit sign-off compliance using the official corporate Excel template (<code>templates/TFSPH_Daily_Backup_Checklist_Template.xlsx</code>).</p>

        <h2>1. Purpose of the Daily Report</h2>
        <p>Toyota Financial Services Philippines (TFSPH) requires a standardized daily verification checklist confirming that all critical production and application backups have completed successfully, hashes have been cryptographically verified, and storage capacity is intact. This report serves as operational proof for internal audits and disaster recovery compliance.</p>

        <h2>2. Master Monitored Systems (Table 1)</h2>
        <p>The system comes pre-configured with the 8 standard TFSPH enterprise systems:</p>
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%; border-color: #E2E8F0;">
            <tr style="background-color: #F8FAFC;">
                <th>No.</th>
                <th>System / Job</th>
                <th>Pattern Convention</th>
                <th>Type</th>
                <th>Description</th>
            </tr>
            <tr><td>1</td><td><b>TFS42PROD</b></td><td><code>TFS42PROD_&lt;YYYYMMDD&gt;</code></td><td>RAR</td><td>Pre-Batch Clean Backup</td></tr>
            <tr><td>2</td><td><b>CSE</b></td><td><code>CSE_BACKUP_&lt;MM-DD-YYYY&gt;</code></td><td>RAR</td><td>PSR (CSE) Backup</td></tr>
            <tr><td>3</td><td><b>TFA</b></td><td><code>TFA_&lt;YYYYMMDD&gt;</code></td><td>RAR</td><td>TFA Application Backup</td></tr>
            <tr><td>4</td><td><b>COGNOS</b></td><td><code>COGNOS_&lt;YYYYMMDD&gt;</code></td><td>RAR</td><td>Cognos Backup</td></tr>
            <tr><td>5</td><td><b>SAP</b></td><td><code>SAP_BACKUP_&lt;MM-DD-YYYY&gt;</code></td><td>RAR</td><td>SAP Backup</td></tr>
            <tr><td>6</td><td><b>GOCANVAS</b></td><td><code>GOCANVAS_BACKUP_&lt;YYYYMMDD&gt;</code></td><td>RAR</td><td>GoCanvas Backup</td></tr>
            <tr><td>7</td><td><b>DPPS</b></td><td><code>DPPS_BACKUP_&lt;YYYYMMDD&gt;</code></td><td>FILE</td><td>DPPS Backup</td></tr>
            <tr><td>8</td><td><b>QMS</b></td><td><code>QMS_BACKUP_&lt;YYYYMMDD&gt;</code></td><td>FILE</td><td>QMS Backup</td></tr>
        </table>

        <h2>3. Key Design Rules & Specifications</h2>
        <ul>
            <li><b>Omission of .zip in Filename (Col B):</b> In accordance with TFSPH standards, filenames in Column B (e.g. <code>TFS42PROD_20260904</code>) do <b>NOT</b> include <code>.zip</code> or <code>.rar</code> extensions, because Column C is the dedicated <b>File Type</b> column.</li>
            <li><b>Automated Integrity Check (Col I):</b> The system automatically populates this column based on live cryptographic SHA-256 hash checks:
                <ul>
                    <li><code>Passed</code>: File transfer completed and SHA-256 checksum matched source file 100%.</li>
                    <li><code>Failed</code>: Transfer failed or checksum mismatch occurred.</li>
                    <li><code>Not Applicable</code>: Job was skipped, cancelled, or has not executed yet.</li>
                </ul>
            </li>
            <li><b>Dynamic Row Expansion:</b> If the supervisor adds more systems beyond the original 8 (e.g., 9 or 10 systems), the generator automatically inserts rows into Table 1, clones exact styling/borders/data validations, and shifts Daily Control Checks and Sign-Off sections down without breaking merged cells.</li>
        </ul>

        <h2>4. Section 2: Automated Daily Control Checks</h2>
        <p>The system automatically evaluates all 7 corporate control checks in real time:</p>
        <ol>
            <li><b>Backup file exists in designated repository:</b> Verified by checking file presence on the target repository disk.</li>
            <li><b>Backup job completed successfully without critical errors:</b> Verified against SQLite error logs and transfer statuses.</li>
            <li><b>File size is within expected range:</b> Confirms all backup archives are non-zero byte files.</li>
            <li><b>Filename follows approved naming convention:</b> Checks adherence to system prefix and date stamping.</li>
            <li><b>Backup archive accessible & integrity check passed:</b> Evaluates SHA-256 cryptographic verification results.</li>
            <li><b>Repository capacity and availability confirmed:</b> Queries the Windows/SMB file system for available free disk space.</li>
            <li><b>Failed or missed backup escalated and documented:</b> Summarizes exceptions in Table 1 remarks.</li>
        </ol>

        <h2>5. Section 3: Sign-Off & Approvals</h2>
        <ul>
            <li><b>Prepared By:</b> Automatically filled with the active Windows operator name (or custom operator name configured in the toolbar).</li>
            <li><b>Checked By:</b> Defaults to <b>Philip M. Bayudan</b> (editable anytime via the Checklist Configurator dialog).</li>
            <li><b>Reviewed By:</b> Reserved blank for management physical/digital signature.</li>
        </ul>

        <h2>6. How to Generate the Report</h2>
        <ul>
            <li><b>Manual Generation:</b> Go to <b>Daily Report</b> in the sidebar navigation, select the desired batch date using the calendar picker, verify the live preview table, and click <b>Generate Report (.xlsx)</b>. The generated Excel workbook will be saved to the <code>reports/</code> folder and opened automatically.</li>
            <li><b>Automated Generation:</b> When <i>Auto-generate report on transfer completion</i> is enabled (default), the system automatically compiles and exports the daily checklist report as soon as all scheduled transfer window jobs finish.</li>
            <li><b>Supervisor Configuration:</b> Click <b>Configure Checklist</b> to add new production systems, modify naming patterns, change the default supervisor sign-off name, or restore factory defaults.</li>
        </ul>

        <h2>7. Linked Job Mapping (Testing & Deployment Agility)</h2>
        <p>In real-world operations, test jobs or staging pipelines may not share the exact name of the official production systems:</p>
        <ul>
            <li><b>Seamless Mapping:</b> The <b>Linked Job</b> field in the Checklist Configurator allows you to map any local or test job name (e.g., <code>001</code>, <code>002</code>, <code>Test_Job_A</code>) directly to an official checklist row (e.g., <code>TFS42PROD</code>, <code>CSE</code>).</li>
            <li><b>Zero Manual Edits:</b> When the test job executes, the report engine automatically routes its transfer statistics, file sizes, and cryptographic checksums directly to the corresponding corporate checklist row.</li>
            <li><b>Production Ready:</b> In final production deployment, simply clear or update the linked job alias to match the live production job identifiers.</li>
        </ul>

        <h2>8. Multi-File Aggregate Size & Timestamp Accuracy</h2>
        <p>For jobs configured to transfer multiple files in direct copy or batched mode:</p>
        <ul>
            <li><b>Total Size Aggregation:</b> The system sums the byte counts across all successful transfer records for the target job on that batch date (<code>sum(r.file_size)</code>), presenting the true total payload (e.g. <code>350.2 MB</code>) instead of individual file snippets or archive overhead.</li>
            <li><b>Latest Completion Timestamp:</b> Column G (<b>Time of Completion</b>) automatically selects the latest completion timestamp among all completed files in that batch (<code>max(completed_at)</code>), giving auditors an accurate record of when the backup cycle truly finished.</li>
        </ul>

        <h2>9. Real-Time Debounced Refresh & Excel File Lock Protection</h2>
        <ul>
            <li><b>600ms Event Debouncer:</b> When transfers finish, Sync Now triggers, or tabs are switched, a 600ms debouncing timer buffers GUI updates, refreshing the live preview table smoothly without stutter or thread locking.</li>
            <li><b>Windows Excel File Lock Safeguard:</b> If the report is open in Microsoft Excel, Windows places an exclusive write lock on the file. Instead of failing with <code>[Errno 13] Permission denied</code>, the system automatically saves the updated report to a fallback workbook (<code>..._latest.xlsx</code>) and notifies the operator via a yellow Warning InfoBar. Once Excel is closed, the primary workbook can be overwritten cleanly.</li>
        </ul>
        """

