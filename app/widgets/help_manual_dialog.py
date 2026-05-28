"""帮助手册对话框 — 显示焊接/上传等界面说明。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
    QVBoxLayout,
)

from app.i18n import tr

_MANUAL_STYLE = """
body { font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; font-size: 13px; line-height: 1.55; color: #d8dee9; }
h1 { font-size: 18px; color: #e8eaf0; margin: 0 0 12px 0; }
h2 { font-size: 15px; color: #9fb7ff; margin: 18px 0 8px 0; border-bottom: 1px solid #2c3a64; padding-bottom: 4px; }
p { margin: 6px 0; }
ul, ol { margin: 6px 0 6px 20px; padding: 0; }
li { margin: 4px 0; }
code { background: #1e2a48; padding: 1px 5px; border-radius: 3px; font-family: Consolas, monospace; font-size: 12px; }
.note { color: #8b9cc8; font-size: 12px; }
.warn { color: #ffb86c; }
"""


class HelpManualDialog(QDialog):
    """只读帮助手册窗口。"""

    def __init__(self, title: str, body_html: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(640, 520)
        self.resize(720, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setReadOnly(True)
        browser.setFont(QFont("Microsoft YaHei", 10))
        browser.setStyleSheet(
            "QTextBrowser { background-color: #11182d; border: 1px solid #2c3a64; border-radius: 6px; }"
        )
        browser.setHtml(f"<style>{_MANUAL_STYLE}</style>{body_html}")
        layout.addWidget(browser, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText(tr("help_close"))
        layout.addWidget(buttons)

        self.setWindowModality(Qt.WindowModality.WindowModal)
