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
        self._title = TitleLabel("Operator Guides & IT Handover", self)
        self._subtitle = BodyLabel(
            "Daily workflow, demo acceptance, deployment, recovery and verified audit findings.",
            self,
        )
        self._subtitle.setWordWrap(True)
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
        from pathlib import Path
        import sys
        from PySide6.QtGui import QTextDocument
        root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
        docs = root / "docs"
        if not docs.exists():
            docs = root / "_internal" / "docs"
        self._sections = []
        guides = [
            ("1. Operator Guide", "OPERATOR_GUIDE.md"),
            ("2. Demo & Acceptance Checklist", "DEMO_CHECKLIST.md"),
            ("3. IT Handover", "IT_HANDOVER.md"),
            ("4. Audit Findings", "AUDIT_REPORT.md"),
            ("5. Performance & Server Setup", "PERFORMANCE_GUIDE.md"),
            ("6. Recorded Performance Results", "PERFORMANCE_RESULTS.md"),
        ]
        for title, filename in guides:
            try:
                markdown = (docs / filename).read_text(encoding="utf-8-sig")
            except OSError:
                markdown = "# Guide unavailable\nKeep the docs folder with the application release. Ask IT to restore the complete installation."
            document = QTextDocument()
            document.setMarkdown(markdown)
            self._sections.append((title, document.toHtml()))
            self._list_widget.addItem(title)

    def _on_section_selected(self, index: int):
        if 0 <= index < len(self._sections):
            self._content_browser.setHtml(self._sections[index][1])
