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
                body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333; }
                h1 { font-size: 20px; color: #005a9e; border-bottom: 1px solid #ccc; padding-bottom: 5px; }
                h2 { font-size: 16px; color: #005a9e; margin-top: 20px; }
                h3 { font-size: 14px; color: #333; font-weight: bold; }
                ul { margin-top: 5px; margin-bottom: 15px; }
                li { margin-bottom: 5px; }
                .highlight { background-color: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-family: monospace; }
                table { border-collapse: collapse; width: 100%; margin-bottom: 15px; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>File Transfer Automation System</h1>
            <p>Welcome to the automated, secure, and resilient file transfer system. This guide explains how to configure and monitor your automated file transfers.</p>
            
            <h2>1. Getting Started</h2>
            <p>To begin transferring files, you must first create a <b>Job</b>.</p>
            <ul>
                <li>Click <b>Add Job</b> in the left navigation menu.</li>
                <li>Give the job a recognizable name (e.g., <i>"Server 1 to Backup"</i>).</li>
                <li>Set the <b>Source Folder</b> (where files will be dropped). You can use local paths or Network Paths (e.g., <code>\\\\Server\\Share</code>).</li>
                <li>Set the <b>Destination Folder</b> (where files will be copied to).</li>
                <li>Click <b>Save</b>.</li>
            </ul>
            <p>Once your job is selected, click the <b>Start Monitoring</b> button on the dashboard to activate the automated transfer engine.</p>
            
            <h2>2. Core Features</h2>
            <ul>
                <li><b>Copy, Never Move:</b> The system <i>copies</i> files to the destination. It will never instantly delete or move your original files.</li>
                <li><b>7-Day Retention:</b> A background cleanup task runs every Monday. It automatically deletes files from the Source directory that are older than 7 days, keeping your storage clean.</li>
                <li><b>File Safety Checks:</b> The system constantly measures file sizes and checks OS locks to ensure it never transfers a file that is still being written to by another program.</li>
            </ul>

            <h2>3. Transfer Windows (Overnight Transfers)</h2>
            <p>By default, files transfer continuously. If you only want files to transfer during specific hours (like overnight), edit your Job and set the Schedule Mode to <b>Transfer Window</b>.</p>
            <p>For example, setting the window from <code>23:00</code> to <code>06:00</code> means files dropped into the folder at 2 PM will sit in the <b>WAITING_FOR_WINDOW</b> status until 11 PM, at which point they will automatically transfer.</p>

            <h2>4. Batch Compression & Encryption</h2>
            <p>The system can compress all currently queued files into a single ZIP file before transferring.</p>
            <ul>
                <li>Enable this feature in the <b>Settings</b> panel.</li>
                <li>ZIP files are secured with AES encryption.</li>
                <li>You can configure the <b>Zip Password</b> in Settings.</li>
                <li>The generated ZIP file is named automatically based on the current timestamp.</li>
            </ul>

            <h2>5. Managing Jobs</h2>
            <p>You can edit or delete existing jobs directly from the interface:</p>
            <ul>
                <li>Use the <b>Edit Job</b> menu item to change paths or transfer windows.</li>
                <li>Click the <b>Trash Can</b> icon next to the Job selector on the dashboard to completely delete a job. <i>Note: This permanently deletes the job and all its transfer history records.</i></li>
            </ul>

            <h2>6. Status Definitions</h2>
            <p>The main dashboard table tracks files through various statuses. Here is what they mean:</p>
            <table>
                <tr><th>Status</th><th>Meaning</th></tr>
                <tr><td><span style="color: #606060; font-weight: bold;">DETECTED</span></td><td>The file has just been noticed in the Source folder.</td></tr>
                <tr><td><span style="color: #005a9e; font-weight: bold;">PROCESSING</span></td><td>The system is watching the file to ensure it has stopped growing and is no longer locked by Windows.</td></tr>
                <tr><td><span style="color: #ca5010; font-weight: bold;">WAITING_FOR_WINDOW</span></td><td>The file is safe, but it is currently outside the permitted Transfer Window. It will wait here.</td></tr>
                <tr><td><span style="color: #005a9e; font-weight: bold;">READY</span></td><td>The file is queued up and ready to be transferred.</td></tr>
                <tr><td><span style="color: #0078d4; font-weight: bold;">TRANSFERRING</span></td><td>The byte-by-byte copy is actively running in the background.</td></tr>
                <tr><td><span style="color: #107c10; font-weight: bold;">COMPLETED</span></td><td>The transfer finished and the integrity hash matched perfectly.</td></tr>
                <tr><td><span style="color: #d13438; font-weight: bold;">FAILED</span></td><td>The transfer failed (network drop, permission issue, etc). It will automatically retry up to 3 times.</td></tr>
            </table>

            <h2>7. Manual Sync</h2>
            <p>If you have monitoring turned off, or if you just want to force a scan, you can click <b>Sync Now</b>. This will scan the folder, process the files, and ask you for confirmation before starting the transfers.</p>
        </body>
        </html>
        """
        self.textBrowser.setHtml(html_content)
