import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon

from linux_chan.gui import ChatBotGUI
from linux_chan.themes import THEMES, DEFAULT_THEME, build_stylesheet

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Linux Chan AI")
    app.setStyleSheet(build_stylesheet(THEMES[DEFAULT_THEME]))
    app.setWindowIcon(
        QIcon(os.path.join(SCRIPT_DIR, "assets", "icons", "linux-chan_mini.png"))
    )

    window = ChatBotGUI()
    window.show()
    sys.exit(app.exec_())
