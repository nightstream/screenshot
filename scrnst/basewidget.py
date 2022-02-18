# coding=utf-8

import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtWidgets import QWidget, QGraphicsView, QGraphicsScene


def _initLogger(obj: QWidget):
    """初始化日志句柄"""
    obj.logger = logging.getLogger(obj.__class__.__name__)
    obj.logger.setLevel(logging.DEBUG)

    fmtstr = "[%(asctime)s] [%(lineno)d] [%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmtstr)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)

    fh = RotatingFileHandler(filename="info.log", backupCount=5,
                             maxBytes=1024 * 1024 * 50, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    obj.logger.addHandler(ch)
    obj.logger.addHandler(fh)


class BaseWidget(QWidget):
    """基础控件"""

    def __init__(self, parent: QWidget = None) -> None:
        """初始化控件"""
        super(BaseWidget, self).__init__(parent=parent)
        _initLogger(self)


class BaseGraphicsView(QGraphicsView):
    """视图"""

    def __init__(self, scene: QGraphicsScene = None, parent: QWidget = None) -> None:
        """初始化控件"""
        super(BaseGraphicsView, self).__init__(scene=scene, parent=parent)
        _initLogger(self)
