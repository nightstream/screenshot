import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from scrnst import makeScreenShot

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

    qtApp = QApplication(sys.argv)
    window = makeScreenShot()
    window.show()
    qtApp.exec()
