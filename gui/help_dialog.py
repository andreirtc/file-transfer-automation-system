from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QVBoxLayout, QTextBrowser
from qfluentwidgets import MessageBoxBase, SubtitleLabel

class UserDocumentationDialog(MessageBoxBase):
    """
    Dialog displaying the comprehensive user guide for the File Transfer Automation System.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel("User Guide", self)
        
        self.textBrowser = QTextBrowser(self)
        self.textBrowser.setOpenExternalLinks(True)
        self.textBrowser.setMinimumSize(QSize(600, 450))
        
        self._setup_content()
        
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.textBrowser)
        
        self.yesButton.setText("Close")
        self.cancelButton.hide()
        
        # Expand the dialog width
        self.widget.setMinimumWidth(650)

    def _setup_content(self):
        html_content = """
        <html>
        <head>
            <style>
                body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; line-height: 1.6; color: #1E293B; }
                h1 { font-size: 19px; color: #005A9E; border-bottom: 2px solid #E2E8F0; padding-bottom: 6px; margin-bottom: 12px; }
                h2 { font-size: 15px; color: #005A9E; margin-top: 18px; margin-bottom: 8px; }
                h3 { font-size: 13px; color: #1E293B; font-weight: 600; margin-top: 10px; }
                ul { margin-top: 4px; margin-bottom: 12px; padding-left: 20px; }
                li { margin-bottom: 4px; }
                code { background-color: #F1F5F9; color: #0F172A; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; font-size: 12px; }
                table { border-collapse: collapse; width: 100%; margin-top: 8px; margin-bottom: 16px; font-size: 12px; }
                th, td { border: 1px solid #E2E8F0; padding: 7px 10px; text-align: left; }
                th { background-color: #F8FAFC; color: #334155; font-weight: 600; }
                .badge { padding: 2px 6px; border-radius: 3px; font-weight: 600; font-size: 11px; }
            </style>
        </head>
        <body>
            <h1>File Transfer Automation System — User Guide</h1>
            <p>Welcome to the Enterprise File Transfer Automation System. This guide provides comprehensive instructions for configuring, monitoring, and managing automated one-way file transfers with end-to-end cryptographic verification.</p>
            
            <h2>1. Getting Started & Creating Jobs</h2>
            <p>The system operates using <b>Transfer Jobs</b>. Each job defines an automated transfer pipeline between a source and a destination directory.</p>
            <ul>
                <li>Click <b>Add Job</b> in the navigation bar or on the Main Dashboard.</li>
                <li><b>Job Name:</b> Enter a descriptive identifier (e.g., <code>Branch A Server Backup</code>).</li>
                <li><b>Source Folder:</b> Directory monitored for new files. Supports local disks or network shares (e.g., <code>\\\\Server\\Backups\\Data</code>).</li>
                <li><b>Destination Folder:</b> Target directory where files will be safely transferred.</li>
                <li><b>Schedule Mode:</b>
                    <ul>
                        <li><b>Continuous:</b> Files are transferred immediately as soon as they stabilize and pass lock checks.</li>
                        <li><b>Transfer Window:</b> Files accumulate during the day and automatically transfer in a single batch when the configured <b>Window End</b> time is reached (ideal for overnight backup windows).</li>
                    </ul>
                </li>
            </ul>

            <h2>2. Multi-Job Concurrency & Global Transfer Queue</h2>
            <p>To maximize throughput while preserving network and disk stability, the system incorporates an intelligent <b>Concurrent Worker Pool</b> and FIFO queue:</p>
            <ul>
                <li>All enabled jobs monitor their source directories concurrently in the background.</li>
                <li>When scheduled window end-times arrive or batch transfers trigger, directory sweeps run in parallel across a thread pool.</li>
                <li>Jobs are queued in strict alphabetical order and dispatched up to <code>max_concurrent_transfers</code> (default: 3 simultaneous jobs).</li>
                <li>Active jobs display <span class="badge" style="background-color: #EFF6FF; color: #1D4ED8;">TRANSFERRING</span>, while subsequent jobs display <span class="badge" style="background-color: #FFFBEB; color: #B45309;">QUEUED (IN LINE)</span>.</li>
                <li>As soon as any active job completes, the next queued job immediately commences transfer without manual intervention.</li>
            </ul>

            <h2>3. Real-Time Live Progress Bars & Instant Reporting</h2>
            <p>Each job card on the Main Dashboard provides a real-time progress bar that dynamically updates through each transfer phase:</p>
            <ul>
                <li><b>Instant 0-Second Display:</b> Precalculates total batch size in memory and flushes <code>0% · 0.0 MB / Total MB</code> on millisecond 0.</li>
                <li><b>Compressing Archive:</b> Shows live percentage progress and byte throughput as files are packaged into the encrypted zip archive.</li>
                <li><b>Transferring Archive:</b> Shows active byte transfer throughput (<code>XX.X MB / YY.Y MB</code>) and transfer speed.</li>
                <li><b>Verifying SHA-256:</b> Displays cryptographic hash verification progress ensuring byte-for-byte data integrity.</li>
            </ul>

            <h2>4. Batch Compression & WinZip AES-256 Encryption</h2>
            <p>When batch compression is enabled, queued files are consolidated into a single password-protected zip file:</p>
            <ul>
                <li><b>Modern AES-256 Encryption:</b> Powered by <code>pyzipper</code> with native Zip64 support for huge archives exceeding 4 GB (up to terabytes). Seamless fallback to <code>pyminizip</code> and standard <code>zipfile</code>.</li>
                <li><b>Automated Naming:</b> Archives are automatically named by date and window start time (e.g., <code>2026-08-19_230000.zip</code>).</li>
                <li><b>Password Configuration:</b> Configure the default archive password in <b>Settings</b>.</li>
                <li><b>Mid-Compression Deletion Safeguard:</b> If any file is deleted from source during active compression, the worker automatically discards the partial archive, logs an announcement, and restarts cleanly with the remaining valid files.</li>
            </ul>

            <h2>5. Dual-Verified Source File Retention</h2>
            <p>The system enforces safe source file cleanup to prevent premature data loss:</p>
            <ul>
                <li><b>Configurable Retention Period:</b> In <b>Settings</b>, configure <b>Cleanup Retention (Days)</b> (range: 1 to 365 days; default: 7 days).</li>
                <li><b>Dual-Verification Rule:</b> Source files are deleted if and only if:
                    <ol>
                        <li>The file was transferred at least <i>N</i> days ago.</li>
                        <li>The transfer is verified as completed and the file exists in the destination.</li>
                        <li>The original file is still detected at the source.</li>
                    </ol>
                </li>
            </ul>

            <h2>6. Status & Lifecycle Reference Guide</h2>
            <p>The system tracks status at two levels: <b>Job Execution State</b> (on Dashboard cards) and <b>File Lifecycle Status</b> (in Job Workspace table):</p>
            
            <h3>Job-Level Execution States (Main Dashboard Badges)</h3>
            <table>
                <tr><th>Badge</th><th>Description</th></tr>
                <tr><td><span class="badge" style="background-color: #EFF6FF; color: #1D4ED8;">TRANSFERRING</span></td><td>Active byte copy, compression, or verification running in background.</td></tr>
                <tr><td><span class="badge" style="background-color: #FFFBEB; color: #B45309;">QUEUED (IN LINE)</span></td><td>Waiting in the Sequential FIFO Queue for an available worker slot.</td></tr>
                <tr><td><span class="badge" style="background-color: #F0FDF4; color: #15803D;">MONITORING</span></td><td>Background file watcher is active and listening for filesystem events.</td></tr>
                <tr><td><span class="badge" style="background-color: #FFFBEB; color: #92400E;">WAITING (OUTSIDE WINDOW)</span></td><td>Files detected and stable; holding until scheduled window end-time.</td></tr>
                <tr><td><span class="badge" style="background-color: #F3F4F6; color: #4B5563;">IDLE / STOPPED</span></td><td>Job monitoring is stopped or paused.</td></tr>
            </table>

            <h3>File-Level Lifecycle Statuses (Job Workspace Table)</h3>
            <table>
                <tr><th>Status</th><th>Meaning & Description</th></tr>
                <tr><td><code>DETECTED</code></td><td>New file discovered; initial lock and stability checks underway.</td></tr>
                <tr><td><code>PROCESSING</code></td><td>File size is being monitored across intervals to ensure it is finished being written.</td></tr>
                <tr><td><code>WAITING_FOR_WINDOW</code></td><td>File is stable and ready, holding until the scheduled backup window.</td></tr>
                <tr><td><code>READY</code></td><td>File is completely written and ready to transfer.</td></tr>
                <tr><td><code>QUEUED</code></td><td>File is queued in memory for an active worker slot.</td></tr>
                <tr><td><code>TRANSFERRING</code></td><td>Bytes are actively copying or compressing into destination archive.</td></tr>
                <tr><td><code>VERIFYING</code></td><td>Computing and matching SHA-256 cryptographic hashes.</td></tr>
                <tr><td><code>COMPLETED</code></td><td>File transfer succeeded and verified 100% identical to source.</td></tr>
                <tr><td><code>FAILED</code></td><td>Transfer error occurred (network disconnect, disk full, etc.). Select and click "Retry Failed".</td></tr>
                <tr><td><code>SKIPPED</code></td><td>Intentionally omitted (e.g. duplicate file already transferred, or deleted by operator).</td></tr>
                <tr><td><code>CONFLICT</code></td><td>File with same name exists at destination with different size/date.</td></tr>
            </table>

            <h2>7. IT Administrator Handbook & Troubleshooting</h2>
            <p>For complete step-by-step operating procedures, network share configuration, and practical troubleshooting scenarios, open the interactive <b>Documentation</b> page in the bottom-left sidebar.</p>
        </body>
        </html>
        """
        self.textBrowser.setHtml(html_content)
