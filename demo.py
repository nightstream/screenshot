import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QLabel
from pyqt_screenshot import Screenshot, constant

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    qtApp = QApplication(sys.argv)

    main_window = QLabel()
    img = Screenshot.take_screenshot(constant.CLIPBOARD)
    main_window.show()
    if img is not None:
        main_window.setPixmap(QPixmap(img))
    qtApp.exec()
